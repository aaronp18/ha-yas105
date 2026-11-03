"""RFCOMM (Bluetooth Classic Serial Port Profile) transport.

The YAS-105 exposes a serial byte stream over RFCOMM; this module owns the socket and
turns it into "send one frame, read frames back". The socket factory is injected so the
test suite never touches real Bluetooth.

Some CPython builds - including the uv-managed python-build-standalone used by this repo
and its container image - are compiled without the BlueZ headers. Their ``socket`` module
has no ``AF_BLUETOOTH``/``BTPROTO_RFCOMM``, and ``socket.connect()`` rejects a Bluetooth
address with ``OSError: bad family`` because CPython never learned to parse
``sockaddr_rc``. The kernel is fine, so the factory falls back to creating the socket with
the Linux numbers and calling ``libc.connect()`` with a hand-built ``sockaddr_rc``. That
keeps the probe usable on a Bluetooth host without rebuilding the interpreter.
"""

import ctypes
import errno
import logging
import os
import select
import socket
import struct
import time
from collections.abc import Callable

from ha_yas105.protocol import FrameReader, formatFrame

logger = logging.getLogger(__name__)

SocketFactory = Callable[[str, int, float], "socket.socket"]

#: Stop collecting frames after this many in one batch (guards against a chatty peer).
MAX_FRAMES_PER_READ = 32

#: Linux values of ``AF_BLUETOOTH`` and ``BTPROTO_RFCOMM``. Interpreter builds without the
#: BlueZ headers do not export them, but the kernel understands the numbers.
LINUX_AF_BLUETOOTH = 31
LINUX_BTPROTO_RFCOMM = 3

#: RFCOMM channels are numbered 1-30 (channel 0 is the multiplexer control channel).
RFCOMM_CHANNELS = range(1, 31)


class TransportError(RuntimeError):
    """Raised when the Bluetooth link cannot be opened or used."""


def hasNativeBluetoothSupport() -> bool:
    """True when this interpreter was built with Bluetooth socket support."""
    return hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")


def packSockaddrRc(address: str, channel: int) -> bytes:
    """Build a C ``struct sockaddr_rc`` for a Bluetooth address and RFCOMM channel.

    ``bdaddr_t`` is stored little-endian, so the six printed octets go on the wire in
    reverse order. ``sa_family_t`` is a C ``unsigned short`` and the trailing pad byte
    keeps the struct at the 10 bytes the kernel expects.
    """
    octets = address.strip().split(":")
    if len(octets) != 6 or any(len(octet) != 2 for octet in octets):
        raise TransportError(
            f"invalid Bluetooth address {address!r}; expected six hex octets like"
            " AA:BB:CC:DD:EE:FF"
        )
    try:
        rawAddress = bytes(int(octet, 16) for octet in octets)
    except ValueError as exc:
        raise TransportError(f"invalid Bluetooth address {address!r}: {exc}") from exc
    if channel not in RFCOMM_CHANNELS:
        raise TransportError(f"invalid RFCOMM channel {channel!r}; expected 1-30")
    return struct.pack("<H6sBx", LINUX_AF_BLUETOOTH, rawAddress[::-1], channel)


def libcConnect(fd: int, sockaddr: bytes) -> int:
    """Call libc ``connect()`` with a pre-built sockaddr.

    A module-level seam so tests never need a Bluetooth adapter. Returns the C return
    value (``0`` on success, ``-1`` on failure) and leaves ``errno`` readable through
    :func:`ctypes.get_errno`.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    connect = libc.connect
    connect.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    connect.restype = ctypes.c_int
    return connect(fd, sockaddr, len(sockaddr))


def connectWithoutBluetoothSupport(
    address: str, channel: int, timeout: float
) -> socket.socket:
    """Open and connect an RFCOMM socket through libc.

    Used when the interpreter was built without BlueZ support: ``socket()`` still accepts
    address family 31, only CPython's Bluetooth address parsing is missing.
    """
    sockaddr = packSockaddrRc(address, channel)

    try:
        sock = socket.socket(
            LINUX_AF_BLUETOOTH, socket.SOCK_STREAM, LINUX_BTPROTO_RFCOMM
        )
    except OSError as exc:
        raise TransportError(
            "Bluetooth RFCOMM sockets are unavailable on this platform"
            " (the interpreter has no socket.AF_BLUETOOTH and the kernel rejected"
            f" address family {LINUX_AF_BLUETOOTH}): {exc}. Run the probe on Linux with"
            " BlueZ, or use --dry-run to inspect the frames."
        ) from exc

    try:
        sock.setblocking(False)
        if libcConnect(sock.fileno(), sockaddr) != 0:
            error = ctypes.get_errno()
            if error not in (errno.EINPROGRESS, errno.EAGAIN):
                raise OSError(error, os.strerror(error))
            poller = select.poll()
            poller.register(sock.fileno(), select.POLLOUT)
            if not poller.poll(int(timeout * 1000)):
                raise TimeoutError(f"no answer within {timeout:g}s")
            error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if error:
                raise OSError(error, os.strerror(error))
        sock.settimeout(timeout)
    except TimeoutError as exc:
        sock.close()
        raise TransportError(
            f"timed out connecting to {address} on RFCOMM channel {channel}"
            f" after {timeout:g}s"
        ) from exc
    except OSError as exc:
        sock.close()
        raise TransportError(
            f"could not connect to {address} on RFCOMM channel {channel}: {exc}"
        ) from exc
    return sock


def defaultSocketFactory(address: str, channel: int, timeout: float) -> socket.socket:
    """Open a connected RFCOMM socket, or raise :class:`TransportError`.

    Prefers CPython's own Bluetooth socket support and falls back to a libc connect when
    the interpreter was built without the BlueZ headers (see the module docstring).
    """
    if not hasNativeBluetoothSupport():
        logger.info(
            "[RFCOMM] this Python build has no socket.AF_BLUETOOTH; connecting through"
            " libc instead"
        )
        return connectWithoutBluetoothSupport(address, channel, timeout)

    try:
        sock = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
    except OSError as exc:
        raise TransportError(
            "Bluetooth RFCOMM sockets are unavailable on this platform"
            " (socket.AF_BLUETOOTH missing or blocked). Run the probe on Linux with"
            " BlueZ, or use --dry-run to inspect the frames."
        ) from exc

    sock.settimeout(timeout)
    try:
        sock.connect((address, channel))
    except OSError as exc:
        sock.close()
        raise TransportError(
            f"could not connect to {address} on RFCOMM channel {channel}: {exc}"
        ) from exc
    return sock


class RfcommTransport:
    """Send frames to the soundbar and read complete frames back."""

    isDryRun = False

    def __init__(
        self,
        address: str,
        channel: int = 1,
        timeout: float = 5.0,
        socketFactory: SocketFactory | None = None,
    ) -> None:
        self.address = address
        self.channel = channel
        self.timeout = timeout
        self.socketFactory = socketFactory or defaultSocketFactory
        self._socket: socket.socket | None = None
        self._reader = FrameReader()
        self._pending: list[bytes] = []

    @property
    def label(self) -> str:
        return f"{self.address} RFCOMM channel {self.channel}"

    @property
    def isConnected(self) -> bool:
        return self._socket is not None

    def connect(self) -> None:
        """Open the RFCOMM link. Raises :class:`TransportError` on failure."""
        if self.isConnected:
            return
        self._socket = self.socketFactory(self.address, self.channel, self.timeout)
        logger.info("[RFCOMM] connected to %s", self.label)

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        except OSError as exc:  # pragma: no cover - closing a dead link
            logger.debug("[RFCOMM] error while closing: %s", exc)
        finally:
            self._socket = None
            self._pending.clear()
            logger.info("[RFCOMM] link closed")

    def __enter__(self) -> RfcommTransport:
        self.connect()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def sendFrame(self, frame: bytes) -> None:
        """Write one frame to the link."""
        sock = self._requireSocket()
        logger.debug("[RFCOMM] TX %s", formatFrame(frame))
        try:
            sock.sendall(frame)
        except OSError as exc:
            raise TransportError(f"Bluetooth write failed: {exc}") from exc

    def readFrame(self, timeout: float | None = None) -> bytes | None:
        """Return the next complete frame, or ``None`` if none arrived in time."""
        if self._pending:
            return self._pending.pop(0)

        sock = self._requireSocket()
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            if deadline is None:
                wait = self.timeout
            else:
                wait = deadline - time.monotonic()
                if wait <= 0:
                    return None

            sock.settimeout(wait)
            try:
                chunk = sock.recv(1024)
            except TimeoutError:
                return None
            except OSError as exc:
                raise TransportError(f"Bluetooth read failed: {exc}") from exc

            if not chunk:
                logger.warning("[RFCOMM] the soundbar closed the link")
                return None

            frames = self._reader.feed(chunk)
            if frames:
                logger.debug(
                    "[RFCOMM] RX %s", ", ".join(formatFrame(f) for f in frames)
                )
                self._pending.extend(frames[1:])
                return frames[0]

    def readFrames(self, timeout: float) -> list[bytes]:
        """Collect frames until the link has been quiet for ``timeout`` seconds."""
        frames: list[bytes] = []
        deadline = time.monotonic() + timeout
        while len(frames) < MAX_FRAMES_PER_READ:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            frame = self.readFrame(remaining)
            if frame is None:
                break
            frames.append(frame)
            deadline = time.monotonic() + timeout
        return frames

    def _requireSocket(self) -> socket.socket:
        if self._socket is None:
            raise TransportError("not connected; call connect() first")
        return self._socket
