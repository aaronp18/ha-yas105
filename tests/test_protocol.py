import pytest

from ha_yas105.protocol import (
    COMMANDS,
    POWER_QUERY,
    FrameReader,
    buildRequestFrame,
    findCommand,
    formatFrame,
    parseHexFrame,
    parseStatusFrame,
    requestChecksum,
    statusChecksum,
    statusChecksumValid,
)

# Frames copied verbatim from docs/yamaha_yas_105_bluetooth_protocol_spec.md section 3.
# They double as the oracle for the checksum rule: see the module docstring.
DOCUMENTED_FRAMES = (
    ("power_query", (0x00, 0x00, 0x00), "CC AA 03 00 00 00 2F"),
    ("power_on", (0x00, 0x01, 0x00), "CC AA 03 00 01 00 2E"),
    ("power_off", (0x00, 0x02, 0x00), "CC AA 03 00 02 00 2D"),
    ("volume_up", (0x00, 0x03, 0x00), "CC AA 03 00 03 00 2C"),
    ("volume_down", (0x00, 0x04, 0x00), "CC AA 03 00 04 00 2B"),
    ("mute_toggle", (0x00, 0x05, 0x00), "CC AA 03 00 05 00 2A"),
    ("input_tv", (0x01, 0x01, 0x00), "CC AA 03 01 01 00 2D"),
    ("input_bd_dvd", (0x01, 0x02, 0x00), "CC AA 03 01 02 00 2C"),
    ("input_analog", (0x01, 0x03, 0x00), "CC AA 03 01 03 00 2B"),
    ("input_bluetooth", (0x01, 0x04, 0x00), "CC AA 03 01 04 00 2A"),
    ("surround_on", (0x02, 0x01, 0x00), "CC AA 03 02 01 00 2C"),
    ("surround_off", (0x02, 0x00, 0x00), "CC AA 03 02 00 00 2D"),
    ("dsp_movie", (0x02, 0x02, 0x00), "CC AA 03 02 02 00 2B"),
    ("dsp_music", (0x02, 0x03, 0x00), "CC AA 03 02 03 00 2A"),
    ("dsp_sports", (0x02, 0x04, 0x00), "CC AA 03 02 04 00 29"),
    ("dsp_game", (0x02, 0x05, 0x00), "CC AA 03 02 05 00 28"),
    ("dsp_tv_program", (0x02, 0x06, 0x00), "CC AA 03 02 06 00 27"),
    ("clear_voice_on", (0x03, 0x01, 0x00), "CC AA 03 03 01 00 2B"),
    ("clear_voice_off", (0x03, 0x00, 0x00), "CC AA 03 03 00 00 2C"),
    ("bass_extension_on", (0x04, 0x01, 0x00), "CC AA 03 04 01 00 2A"),
    ("bass_extension_off", (0x04, 0x00, 0x00), "CC AA 03 04 00 00 2B"),
    ("subwoofer_up", (0x05, 0x01, 0x00), "CC AA 03 05 01 00 29"),
    ("subwoofer_down", (0x05, 0x02, 0x00), "CC AA 03 05 02 00 28"),
)

#: A 13-byte status frame built from the spec's byte map (power on, Bluetooth input,
#: surround, mute + bass extension set, volume 10, subwoofer 2).
STATUS_FRAME = bytes.fromhex("CCAA0900010401050A020000E0")


@pytest.mark.parametrize(("key", "payload", "expected"), DOCUMENTED_FRAMES)
def test_documented_request_frames(key, payload, expected):
    assert formatFrame(buildRequestFrame(*payload)) == expected

    command = findCommand(key)
    assert command is not None
    assert formatFrame(command.toFrame()) == expected


def test_commands_table_holds_every_documented_button():
    assert len(COMMANDS) == len(DOCUMENTED_FRAMES)
    assert [command.key for command in COMMANDS] == [
        key for key, _, _ in DOCUMENTED_FRAMES
    ]
    assert len({command.key for command in COMMANDS}) == len(COMMANDS)
    assert POWER_QUERY is COMMANDS[0]


def test_find_command_returns_none_for_unknown_key():
    assert findCommand("definitely_not_a_button") is None


def test_checksum_rule_conflicts_with_spec_prose():
    """The spec's prose formula does not reproduce its own table (see docs/protocol.md)."""
    prose = (0x100 - ((0x03 + 0x00 + 0x01 + 0x00) % 0x100)) % 0x100

    assert requestChecksum(0x00, 0x01, 0x00) == 0x2E
    assert prose == 0xFC


def test_parse_status_frame_decodes_documented_byte_map():
    state = parseStatusFrame(STATUS_FRAME)

    assert state.checksum_valid is True
    assert state.power == "ON"
    assert state.input_name == "BLUETOOTH"
    assert state.dsp_mode == "Surround"
    assert state.mute is True
    assert state.clear_voice is False
    assert state.bass_extension is True
    assert state.volume == 10
    assert state.subwoofer_level == 2
    assert state.system_flags == b"\x00\x00"


def test_parse_status_frame_reports_bad_checksum_without_raising():
    corrupted = STATUS_FRAME[:-1] + b"\x00"

    state = parseStatusFrame(corrupted)

    assert state.checksum_valid is False
    assert state.volume == 10


def test_status_checksum_is_twos_complement_over_payload():
    assert statusChecksum(STATUS_FRAME) == STATUS_FRAME[-1]
    assert statusChecksumValid(STATUS_FRAME) is True
    assert statusChecksumValid(STATUS_FRAME[:-1] + b"\x00") is False


@pytest.mark.parametrize(
    "frame",
    [
        STATUS_FRAME[:-1],
        b"\x00\x00" + STATUS_FRAME[2:],
        STATUS_FRAME[:3] + b"\x07" + STATUS_FRAME[4:],
    ],
    ids=["short", "bad-header", "bad-frame-type"],
)
def test_parse_status_frame_rejects_malformed_frames(frame):
    with pytest.raises(ValueError):
        parseStatusFrame(frame)


def test_describe_marks_unknown_values():
    frame = bytearray(STATUS_FRAME)
    frame[4] = 0x09
    frame[5] = 0x09
    frame[6] = 0x09
    frame[-1] = statusChecksum(bytes(frame))

    text = parseStatusFrame(bytes(frame)).describe()

    assert "UNKNOWN (0x09)" in text
    assert "input:          UNKNOWN (0x09)" in text
    assert "dsp:            UNKNOWN (0x09)" in text


class TestFrameReader:
    def test_waits_for_the_rest_of_a_frame(self):
        reader = FrameReader()

        assert reader.feed(STATUS_FRAME[:6]) == []
        assert reader.buffered == STATUS_FRAME[:6]

        assert reader.feed(STATUS_FRAME[6:]) == [STATUS_FRAME]
        assert reader.buffered == b""

    def test_returns_every_frame_in_one_chunk(self):
        reader = FrameReader()

        frames = reader.feed(STATUS_FRAME + STATUS_FRAME)

        assert frames == [STATUS_FRAME, STATUS_FRAME]

    def test_resynchronises_on_the_header(self):
        reader = FrameReader()

        frames = reader.feed(b"\xff\x00garbage" + STATUS_FRAME)

        assert frames == [STATUS_FRAME]

    def test_keeps_a_possible_partial_header(self):
        reader = FrameReader()

        assert reader.feed(b"\x00\xcc") == []
        assert reader.buffered == b"\xcc"

        assert reader.feed(b"\xaa" + STATUS_FRAME[2:]) == [STATUS_FRAME]

    def test_drops_implausible_lengths(self):
        reader = FrameReader()

        assert reader.feed(b"\xcc\xaa\xff\x00") == []
        assert reader.buffered == b"\xaa\xff\x00"

        assert reader.feed(STATUS_FRAME) == [STATUS_FRAME]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CC AA 03 00 00 00 2F", POWER_QUERY.toFrame()),
        ("ccaa030000002f", POWER_QUERY.toFrame()),
        ("0xCC 0xAA,0x03 0x00 0x00 0x00 0x2F", POWER_QUERY.toFrame()),
    ],
)
def test_parse_hex_frame_accepts_common_input_styles(text, expected):
    assert parseHexFrame(text) == expected


@pytest.mark.parametrize("text", ["CC AA 0", "not hex", "CC ZZ"])
def test_parse_hex_frame_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parseHexFrame(text)
