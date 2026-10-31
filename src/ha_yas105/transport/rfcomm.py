"""RFCOMM (Bluetooth Classic Serial Port Profile) transport.

The YAS-105 exposes a serial byte stream over RFCOMM; this module owns the socket and
turns it into "send one frame, read frames back". The socket factory is injected so the
test suite never touches real Bluetooth.
"""

import logging
import socket
import time
from collections.abc import Callable

from ha_yas105.protocol import FrameReader, formatFrame

logger = logging.getLogger(__name__)

SocketFactory = Callable[[str, int, float], "socket.socket"]

#: Stop collecting frames after this many in one batch (guards against a chatty peer).
MAX_FRAMES_PER_READ = 32


class TransportError(RuntimeError):
    """Raised when the Bluetooth link cannot be opened or used."""


def defaultSocketFactory(address: str, channel: int, timeout: float) -> socket.socket:
    """Open a connected RFCOMM socket, or raise :class:`TransportError`."""
    try:
        sock = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        )
    except (AttributeError, OSError) as exc:
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
