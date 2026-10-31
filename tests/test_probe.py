import pytest

from ha_yas105.probe import DryRunTransport, ProtocolProbe
from ha_yas105.protocol import COMMANDS, findCommand, formatFrame
from ha_yas105.transport.rfcomm import TransportError

STATUS_FRAME = bytes.fromhex("CCAA0900010401050A020000E0")


class FakeTransport:
    """In-memory stand-in for :class:`RfcommTransport`."""

    isDryRun = False
    label = "fake link"

    def __init__(self, responses=(), connectError=None):
        self.responses = list(responses)
        self.connectError = connectError
        self.sent = []
        self.connected = False
        self.closed = False
        self.readCalls = []

    def connect(self):
        if self.connectError is not None:
            raise self.connectError
        self.connected = True

    def close(self):
        self.closed = True

    def sendFrame(self, frame):
        self.sent.append(frame)

    def readFrames(self, timeout):
        self.readCalls.append(timeout)
        frames, self.responses = self.responses, []
        return frames


def runProbe(transport, lines, timeout=0.05):
    """Drive the console with scripted input, returning (exit code, transcript)."""
    pending = list(lines)
    transcript = []

    def reader(_prompt):
        if not pending:
            raise EOFError
        return pending.pop(0)

    probe = ProtocolProbe(
        transport, timeout=timeout, inputFunc=reader, outputFunc=transcript.append
    )
    return probe.run(), "\n".join(transcript)


def test_menu_lists_every_button_and_connects():
    transport = FakeTransport()

    code, output = runProbe(transport, ["q"])

    assert code == 0
    assert transport.connected is True
    assert transport.closed is True
    for command in COMMANDS:
        assert command.label in output
        assert formatFrame(command.toFrame()) in output


def test_selecting_a_number_sends_that_frame():
    transport = FakeTransport()

    _, output = runProbe(transport, ["2"])

    assert transport.sent == [findCommand("power_on").toFrame()]
    assert "> Power ON" in output
    assert "TX CC AA 03 00 01 00 2E" in output


def test_command_name_is_accepted_too():
    transport = FakeTransport()

    runProbe(transport, ["mute_toggle"])

    assert transport.sent == [findCommand("mute_toggle").toFrame()]


@pytest.mark.parametrize(
    ("key", "number"),
    [(command.key, index) for index, command in enumerate(COMMANDS, 1)],
)
def test_every_menu_number_maps_to_the_documented_frame(key, number):
    transport = FakeTransport()

    runProbe(transport, [str(number)])

    assert transport.sent == [findCommand(key).toFrame()]


def test_status_response_is_decoded_and_printed():
    transport = FakeTransport(responses=[STATUS_FRAME])

    _, output = runProbe(transport, ["1"])

    assert transport.readCalls == [0.05]
    assert formatFrame(STATUS_FRAME) in output
    assert "checksum: valid" in output
    assert "power:          ON" in output
    assert "input:          BLUETOOTH" in output
    assert "volume:         10" in output


def test_short_response_is_reported_as_unexpected():
    transport = FakeTransport(responses=[b"\xcc\xaa\x03\x00\x00\x00\x2f"])

    _, output = runProbe(transport, ["1"])

    assert "(not the 13-byte status frame the spec describes)" in output


def test_bad_checksum_is_flagged_but_state_is_still_shown():
    transport = FakeTransport(responses=[STATUS_FRAME[:-1] + b"\x00"])

    _, output = runProbe(transport, ["1"])

    assert "checksum: INVALID" in output
    assert "volume:         10" in output


def test_no_response_explains_what_to_try_next():
    transport = FakeTransport()

    _, output = runProbe(transport, ["1"])

    assert "RX nothing within 0.1s" in output
    assert "Try 'w' to listen." in output


def test_raw_hex_frame_is_sent():
    transport = FakeTransport()

    runProbe(transport, ["r", "cc aa 03 00 00 00 2f"])

    assert transport.sent == [bytes.fromhex("ccaa030000002f")]


def test_invalid_raw_hex_is_rejected():
    transport = FakeTransport()

    _, output = runProbe(transport, ["r", "zz"])

    assert transport.sent == []
    assert "[error]" in output


def test_unknown_choice_warns_without_sending():
    transport = FakeTransport()

    _, output = runProbe(transport, ["nope"])

    assert transport.sent == []
    assert "unknown choice 'nope'" in output


def test_number_outside_the_menu_warns():
    transport = FakeTransport()

    _, output = runProbe(transport, ["999"])

    assert transport.sent == []
    assert "there is no button 999" in output


def test_listen_prints_frames_pushed_by_the_soundbar():
    transport = FakeTransport(responses=[STATUS_FRAME])

    _, output = runProbe(transport, ["w", "1"])

    assert transport.sent == []
    assert "listening for 1.0s" in output
    assert "power:          ON" in output
    assert "volume:         10" in output


def test_listen_with_nothing_pushed_says_so():
    transport = FakeTransport()

    _, output = runProbe(transport, ["w", ""])

    assert "RX nothing within 3.0s" in output


def test_help_and_menu_keys_do_not_send():
    transport = FakeTransport()

    _, output = runProbe(transport, ["h", "l"])

    assert transport.sent == []
    assert "Other keys:" in output
    assert "Buttons (type the number, or the command name):" in output


def test_connect_failure_returns_error_code():
    transport = FakeTransport(connectError=TransportError("adapter unhappy"))

    code, output = runProbe(transport, ["1"])

    assert code == 1
    assert "[error] adapter unhappy" in output
    assert transport.sent == []


def test_send_failure_is_reported_and_the_menu_keeps_running():
    class BrokenTransport(FakeTransport):
        def sendFrame(self, _frame):
            raise TransportError("link dropped")

    transport = BrokenTransport()

    code, output = runProbe(transport, ["1", "q"])

    assert code == 0
    assert "[error] link dropped" in output
    assert transport.closed is True


def test_eof_quits_cleanly():
    transport = FakeTransport()

    code, _ = runProbe(transport, [])

    assert code == 0
    assert transport.closed is True


def test_dry_run_transport_records_frames_and_never_reads():
    transport = DryRunTransport()

    code, output = runProbe(transport, ["2", "w", "q"])

    assert code == 0
    assert transport.sent == [findCommand("power_on").toFrame()]
    assert transport.closed is True
    assert "dry run" in output
    assert "nothing to listen to without a Bluetooth link" in output
