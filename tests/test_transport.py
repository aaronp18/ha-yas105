import errno
import struct
from types import SimpleNamespace

import pytest

from ha_yas105.protocol import POWER_QUERY
from ha_yas105.transport.rfcomm import (
    RfcommTransport,
    TransportError,
    defaultSocketFactory,
    packSockaddrRc,
)

STATUS_FRAME = bytes.fromhex("CCAA0900010401050A020000E0")
ADDRESS = "AA:BB:CC:DD:EE:FF"


class FakeSocket:
    """Stand-in for a connected RFCOMM socket. Never touches Bluetooth."""

    def __init__(self, chunks=(), connectError=None, socketError=0):
        self.chunks = list(chunks)
        self.connectError = connectError
        self.socketError = socketError
        self.sent = []
        self.timeouts = []
        self.blocking = []
        self.connectedTo = None
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def setblocking(self, value):
        self.blocking.append(value)

    def fileno(self):
        return 7

    def getsockopt(self, _level, _option):
        return self.socketError

    def connect(self, address):
        if self.connectError is not None:
            raise self.connectError
        self.connectedTo = address

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _size):
        if not self.chunks:
            raise TimeoutError("timed out")
        chunk = self.chunks.pop(0)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk

    def close(self):
        self.closed = True


def makeTransport(chunks=(), channel=1, timeout=0.05):
    """Build a transport backed by a fake socket plus the recorded factory calls."""
    sock = FakeSocket(chunks)
    calls = []

    def factory(address, channel, timeout):
        calls.append((address, channel, timeout))
        return sock

    transport = RfcommTransport(
        ADDRESS, channel, timeout=timeout, socketFactory=factory
    )
    return transport, sock, calls


def test_connect_opens_the_configured_channel():
    transport, sock, calls = makeTransport(channel=3, timeout=0.05)

    transport.connect()

    # The socket factory owns the actual connect(); the transport only asks for it.
    assert calls == [(ADDRESS, 3, 0.05)]
    assert sock.closed is False
    assert transport.isConnected is True
    assert transport.label == f"{ADDRESS} RFCOMM channel 3"


def test_send_frame_writes_the_exact_bytes():
    transport, sock, _ = makeTransport()
    transport.connect()

    transport.sendFrame(POWER_QUERY.toFrame())

    assert sock.sent == [b"\xcc\xaa\x03\x00\x00\x00\x2f"]


def test_send_before_connect_raises_transport_error():
    transport, _, _ = makeTransport()

    with pytest.raises(TransportError):
        transport.sendFrame(POWER_QUERY.toFrame())


def test_read_frame_reassembles_a_split_frame():
    transport, _, _ = makeTransport([STATUS_FRAME[:5], STATUS_FRAME[5:]])
    transport.connect()

    assert transport.readFrame(0.05) == STATUS_FRAME


def test_read_frame_returns_none_when_the_link_stays_quiet():
    transport, _, _ = makeTransport()
    transport.connect()

    assert transport.readFrame(0.01) is None


def test_read_frame_ignores_bytes_before_the_header():
    transport, _, _ = makeTransport([b"\x01\x02" + STATUS_FRAME])
    transport.connect()

    assert transport.readFrame(0.05) == STATUS_FRAME


def test_read_frames_collects_frames_until_the_link_is_quiet():
    transport, _, _ = makeTransport([STATUS_FRAME + STATUS_FRAME])
    transport.connect()

    assert transport.readFrames(0.01) == [STATUS_FRAME, STATUS_FRAME]


def test_read_frames_returns_empty_list_without_any_frame():
    transport, _, _ = makeTransport()
    transport.connect()

    assert transport.readFrames(0.01) == []


def test_read_errors_are_wrapped():
    transport, _, _ = makeTransport([OSError("adapter gone")])
    transport.connect()

    with pytest.raises(TransportError):
        transport.readFrame(0.05)


def test_close_is_idempotent_and_reports_disconnected():
    transport, sock, _ = makeTransport()
    transport.connect()

    transport.close()
    transport.close()

    assert sock.closed is True
    assert transport.isConnected is False


def test_context_manager_connects_and_closes():
    transport, sock, _ = makeTransport()

    with transport as entered:
        assert entered is transport
        assert transport.isConnected is True

    assert sock.closed is True


class FakeSocketModule:
    """Stand-in for the ``socket`` module so tests do not need a Bluetooth kernel."""

    AF_BLUETOOTH = 31
    SOCK_STREAM = 1
    BTPROTO_RFCOMM = 3

    def __init__(self, sock=None, error=None):
        self._sock = sock
        self._error = error

    def socket(self, *_args):
        if self._error is not None:
            raise self._error
        return self._sock


def test_default_factory_reports_missing_bluetooth_stack(monkeypatch):
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket",
        FakeSocketModule(error=OSError("Address family not supported")),
    )

    with pytest.raises(TransportError, match="unavailable on this platform"):
        defaultSocketFactory(ADDRESS, 1, 1.0)


class BluetoothlessSocketModule:
    """``socket`` module of an interpreter built without BlueZ support."""

    SOCK_STREAM = 1
    SOL_SOCKET = 1
    SO_ERROR = 4

    def __init__(self, sock=None, error=None):
        self._sock = sock
        self._error = error
        self.calls = []

    def socket(self, *args):
        self.calls.append(args)
        if self._error is not None:
            raise self._error
        return self._sock


def test_default_factory_delegates_to_libc_without_af_bluetooth(monkeypatch):
    fallbackCalls = []

    def fallback(address, channel, timeout):
        fallbackCalls.append((address, channel, timeout))
        return "connected through libc"

    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket", BluetoothlessSocketModule()
    )
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.connectWithoutBluetoothSupport", fallback
    )

    assert defaultSocketFactory(ADDRESS, 2, 0.25) == "connected through libc"
    assert fallbackCalls == [(ADDRESS, 2, 0.25)]


def test_default_factory_wraps_connect_failures(monkeypatch):
    sock = FakeSocket(connectError=OSError("host is down"))
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket", FakeSocketModule(sock=sock)
    )

    with pytest.raises(TransportError, match="channel 1"):
        defaultSocketFactory(ADDRESS, 1, 1.0)

    assert sock.closed is True


def test_default_factory_returns_a_connected_socket(monkeypatch):
    sock = FakeSocket()
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket", FakeSocketModule(sock=sock)
    )

    assert defaultSocketFactory(ADDRESS, 2, 0.25) is sock
    assert sock.connectedTo == (ADDRESS, 2)
    assert sock.timeouts == [0.25]


# ---------------------------------------------------------------------------
# libc fallback for interpreters built without AF_BLUETOOTH (uv's Python 3.14)
# ---------------------------------------------------------------------------


def test_pack_sockaddr_rc_reverses_the_mac_and_uses_linux_family_31():
    packed = packSockaddrRc(ADDRESS, 3)

    assert packed == struct.pack("<H6sBx", 31, bytes.fromhex("FFEEDDCCBBAA"), 3)
    assert len(packed) == 10


@pytest.mark.parametrize(
    "address",
    ["", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "AA:BB:CC:DD:EE:FFFF", "nonsense"],
)
def test_pack_sockaddr_rc_rejects_malformed_addresses(address):
    with pytest.raises(TransportError, match="invalid Bluetooth address"):
        packSockaddrRc(address, 1)


@pytest.mark.parametrize("channel", [0, -1, 31])
def test_pack_sockaddr_rc_rejects_channels_outside_1_to_30(channel):
    with pytest.raises(TransportError, match="invalid RFCOMM channel"):
        packSockaddrRc(ADDRESS, channel)


def test_libc_fallback_connects_with_raw_linux_numbers(monkeypatch):
    sock = FakeSocket()
    module = BluetoothlessSocketModule(sock=sock)
    connects = []

    def fakeLibcConnect(fd, sockaddr):
        connects.append((fd, sockaddr))
        return 0

    monkeypatch.setattr("ha_yas105.transport.rfcomm.socket", module)
    monkeypatch.setattr("ha_yas105.transport.rfcomm.libcConnect", fakeLibcConnect)

    assert defaultSocketFactory(ADDRESS, 3, 0.25) is sock
    assert module.calls == [(31, 1, 3)]
    assert connects == [(7, packSockaddrRc(ADDRESS, 3))]
    assert sock.blocking == [False]
    assert sock.timeouts == [0.25]
    assert sock.closed is False


def test_libc_fallback_reports_a_kernel_without_bluetooth(monkeypatch):
    module = BluetoothlessSocketModule(
        error=OSError(errno.EAFNOSUPPORT, "Address family not supported")
    )
    monkeypatch.setattr("ha_yas105.transport.rfcomm.socket", module)

    with pytest.raises(TransportError, match="unavailable on this platform"):
        defaultSocketFactory(ADDRESS, 1, 0.5)

    assert module.calls == [(31, 1, 3)]


def test_libc_fallback_wraps_immediate_connect_errors(monkeypatch):
    sock = FakeSocket()
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket", BluetoothlessSocketModule(sock=sock)
    )
    monkeypatch.setattr("ha_yas105.transport.rfcomm.libcConnect", lambda *_: -1)
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.ctypes",
        SimpleNamespace(get_errno=lambda: errno.EHOSTUNREACH),
    )

    with pytest.raises(TransportError, match="could not connect to") as excinfo:
        defaultSocketFactory(ADDRESS, 1, 0.5)

    # strerror() wording is platform specific; the errno is not.
    assert f"[Errno {errno.EHOSTUNREACH}]" in str(excinfo.value)
    assert sock.closed is True


def test_libc_fallback_times_out_while_the_link_is_pending(monkeypatch):
    sock = FakeSocket()

    class SilentPoll:
        def register(self, *_args):
            pass

        def poll(self, _timeout):
            return []

    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket", BluetoothlessSocketModule(sock=sock)
    )
    monkeypatch.setattr("ha_yas105.transport.rfcomm.libcConnect", lambda *_: -1)
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.ctypes",
        SimpleNamespace(get_errno=lambda: errno.EINPROGRESS),
    )
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.select",
        SimpleNamespace(poll=SilentPoll, POLLOUT=4),
    )

    with pytest.raises(TransportError, match="timed out connecting") as excinfo:
        defaultSocketFactory(ADDRESS, 1, 0.5)

    assert "after 0.5s" in str(excinfo.value)
    assert sock.closed is True


def test_libc_fallback_reports_the_socket_error_found_after_polling(monkeypatch):
    sock = FakeSocket(socketError=errno.ECONNREFUSED)

    class ReadyPoll:
        def register(self, *_args):
            pass

        def poll(self, _timeout):
            return [(7, 4)]

    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.socket", BluetoothlessSocketModule(sock=sock)
    )
    monkeypatch.setattr("ha_yas105.transport.rfcomm.libcConnect", lambda *_: -1)
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.ctypes",
        SimpleNamespace(get_errno=lambda: errno.EINPROGRESS),
    )
    monkeypatch.setattr(
        "ha_yas105.transport.rfcomm.select",
        SimpleNamespace(poll=ReadyPoll, POLLOUT=4),
    )

    with pytest.raises(TransportError, match="could not connect to") as excinfo:
        defaultSocketFactory(ADDRESS, 1, 0.5)

    assert f"[Errno {errno.ECONNREFUSED}]" in str(excinfo.value)
    assert sock.closed is True
