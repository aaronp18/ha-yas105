import pytest

from ha_yas105.protocol import POWER_QUERY
from ha_yas105.transport.rfcomm import (
    RfcommTransport,
    TransportError,
    defaultSocketFactory,
)

STATUS_FRAME = bytes.fromhex("CCAA0900010401050A020000E0")
ADDRESS = "AA:BB:CC:DD:EE:FF"


class FakeSocket:
    """Stand-in for a connected RFCOMM socket. Never touches Bluetooth."""

    def __init__(self, chunks=(), connectError=None):
        self.chunks = list(chunks)
        self.connectError = connectError
        self.sent = []
        self.timeouts = []
        self.connectedTo = None
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

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


def test_default_factory_reports_a_stack_without_af_bluetooth(monkeypatch):
    class NoBluetoothStack:
        SOCK_STREAM = 1
        BTPROTO_RFCOMM = 3

        def socket(self, *_args):  # pragma: no cover - must never be called
            raise AssertionError("socket() must not be reached")

    monkeypatch.setattr("ha_yas105.transport.rfcomm.socket", NoBluetoothStack())

    with pytest.raises(TransportError, match="unavailable on this platform"):
        defaultSocketFactory(ADDRESS, 1, 1.0)


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
