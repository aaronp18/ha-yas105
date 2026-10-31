"""Hypothesised YAS-105 Bluetooth protocol.

Everything here comes from ``docs/yamaha_yas_105_bluetooth_protocol_spec.md`` (a Gemini
conversation). It has **not** been confirmed against the soundbar: see
``docs/protocol.md``, where the only confirmed fact is still "the control link is an
RFCOMM byte stream". Treat every frame in this module as a hypothesis to be tested with
``ha-yas105 probe`` and recorded in ``docs/protocol.md`` before any feature is built on
top of it.

Known inconsistency in the source document:

* The prose says
  ``checksum = (0x100 - (sum of payload bytes % 0x100)) % 0x100`` over "all payload
  bytes excluding the header". Applied to ``CC AA 03 00 01 00 ??`` that yields ``FC``.
* The table in the same document prints ``2E`` for that frame. All 23 documented frames
  satisfy ``(0x2F - (category + subcommand + data)) & 0xFF`` instead.

:func:`requestChecksum` implements the rule that reproduces the documented frames.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Fixed two-byte frame header (both directions).
HEADER = b"\xcc\xaa"

#: Length byte of a request frame: three payload bytes follow it.
REQUEST_PAYLOAD_LENGTH = 0x03

#: Length byte of a status frame: nine payload bytes follow it.
STATUS_PAYLOAD_LENGTH = 0x09

#: Frame type byte of a status notification frame.
STATUS_FRAME_TYPE = 0x00

#: Total size of a status frame: header + length + payload + checksum.
STATUS_FRAME_LENGTH = 2 + 1 + STATUS_PAYLOAD_LENGTH + 1

#: Total size of a request frame: header + length + payload + checksum.
REQUEST_FRAME_LENGTH = 2 + 1 + REQUEST_PAYLOAD_LENGTH + 1

#: Constant of the checksum rule that reproduces every documented request frame.
REQUEST_CHECKSUM_BASE = 0x2F

#: Sanity bound when resynchronising: no documented frame is anywhere near this long.
MAX_PAYLOAD_LENGTH = 0x40

INPUT_NAMES = {
    0x01: "TV (optical)",
    0x02: "BD/DVD (coax)",
    0x03: "ANALOG (aux)",
    0x04: "BLUETOOTH",
}

DSP_NAMES = {
    0x00: "Stereo",
    0x01: "Surround",
    0x02: "Music",
    0x03: "Sports",
    0x04: "Game",
    0x05: "TV Program",
}


def formatFrame(frame: bytes) -> str:
    """Render bytes as an upper-case, space separated hex string."""
    return " ".join(f"{byte:02X}" for byte in frame)


def parseHexFrame(text: str) -> bytes:
    """Parse a user supplied hex string such as ``CC AA 03 00 00 00 2F``.

    Accepts spaces, commas, ``0x`` prefixes and a contiguous string. Raises
    :class:`ValueError` for anything that is not a whole number of hex bytes.
    """
    cleaned = text.replace(",", " ").replace("0x", " ").replace("0X", " ")
    return bytes.fromhex(cleaned)


def requestChecksum(category: int, subcommand: int, data: int = 0) -> int:
    """Checksum byte for a request frame.

    Matches every frame printed in the source document's command table, and does *not*
    match the two's complement formula described in its prose. See the module docstring.
    """
    return (REQUEST_CHECKSUM_BASE - (category + subcommand + data)) & 0xFF


def buildRequestFrame(category: int, subcommand: int, data: int = 0) -> bytes:
    """Build a request frame: ``CC AA 03 <category> <subcommand> <data> <checksum>``."""
    payload = bytes((category & 0xFF, subcommand & 0xFF, data & 0xFF))
    return (
        HEADER
        + bytes((REQUEST_PAYLOAD_LENGTH,))
        + payload
        + bytes((requestChecksum(*payload),))
    )


def statusChecksum(frame: bytes) -> int:
    """Two's complement checksum over a status frame, excluding the 2-byte header.

    This follows the source document's prose formula for inbound frames (§4). No
    example inbound frame exists yet, so this too is unverified.
    """
    payload = frame[2:-1]
    return (0x100 - (sum(payload) % 0x100)) % 0x100


def statusChecksumValid(frame: bytes) -> bool:
    """Whether ``frame[-1]`` matches :func:`statusChecksum`."""
    return len(frame) >= 4 and statusChecksum(frame) == frame[-1]


@dataclass(frozen=True, slots=True)
class Command:
    """One documented "button" that can be sent to the soundbar."""

    key: str
    label: str
    group: str
    category: int
    subcommand: int
    data: int = 0

    def toFrame(self) -> bytes:
        """Serialise this command into its RFCOMM request frame."""
        return buildRequestFrame(self.category, self.subcommand, self.data)


#: Every command in the source document's table, in document order.
COMMANDS: tuple[Command, ...] = (
    Command("power_query", "Power query", "Power", 0x00, 0x00),
    Command("power_on", "Power ON", "Power", 0x00, 0x01),
    Command("power_off", "Power OFF (standby)", "Power", 0x00, 0x02),
    Command("volume_up", "Master volume UP", "Volume", 0x00, 0x03),
    Command("volume_down", "Master volume DOWN", "Volume", 0x00, 0x04),
    Command("mute_toggle", "Mute toggle", "Volume", 0x00, 0x05),
    Command("input_tv", "Input: TV (optical)", "Input", 0x01, 0x01),
    Command("input_bd_dvd", "Input: BD/DVD (coax)", "Input", 0x01, 0x02),
    Command("input_analog", "Input: ANALOG (aux)", "Input", 0x01, 0x03),
    Command("input_bluetooth", "Input: BLUETOOTH", "Input", 0x01, 0x04),
    Command("surround_on", "Surround: ON", "Sound", 0x02, 0x01),
    Command("surround_off", "Surround: OFF (stereo)", "Sound", 0x02, 0x00),
    Command("dsp_movie", "DSP: Movie", "Sound", 0x02, 0x02),
    Command("dsp_music", "DSP: Music", "Sound", 0x02, 0x03),
    Command("dsp_sports", "DSP: Sports", "Sound", 0x02, 0x04),
    Command("dsp_game", "DSP: Game", "Sound", 0x02, 0x05),
    Command("dsp_tv_program", "DSP: TV Program", "Sound", 0x02, 0x06),
    Command("clear_voice_on", "Clear Voice: ON", "Sound", 0x03, 0x01),
    Command("clear_voice_off", "Clear Voice: OFF", "Sound", 0x03, 0x00),
    Command("bass_extension_on", "Bass Extension: ON", "Sound", 0x04, 0x01),
    Command("bass_extension_off", "Bass Extension: OFF", "Sound", 0x04, 0x00),
    Command("subwoofer_up", "Subwoofer volume UP", "Subwoofer", 0x05, 0x01),
    Command("subwoofer_down", "Subwoofer volume DOWN", "Subwoofer", 0x05, 0x02),
)

#: Alias kept for readability at call sites that just want the state query.
POWER_QUERY = COMMANDS[0]


def findCommand(key: str) -> Command | None:
    """Look a command up by its stable key (``power_on``, ``dsp_music``, ...)."""
    for command in COMMANDS:
        if command.key == key:
            return command
    return None


@dataclass(frozen=True, slots=True)
class SoundbarState:
    """Decoded 13-byte status frame as described by the source document (§4)."""

    raw: bytes
    checksum_valid: bool
    power_raw: int
    input_raw: int
    dsp_raw: int
    feature_flags: int
    volume: int
    subwoofer_level: int
    system_flags: bytes

    @property
    def power(self) -> str:
        return {0x01: "ON", 0x02: "OFF"}.get(self.power_raw, "UNKNOWN")

    @property
    def input_name(self) -> str:
        return INPUT_NAMES.get(self.input_raw, "UNKNOWN")

    @property
    def dsp_mode(self) -> str:
        return DSP_NAMES.get(self.dsp_raw, "UNKNOWN")

    @property
    def mute(self) -> bool:
        return bool(self.feature_flags & 0x01)

    @property
    def clear_voice(self) -> bool:
        return bool(self.feature_flags & 0x02)

    @property
    def bass_extension(self) -> bool:
        return bool(self.feature_flags & 0x04)

    def describe(self) -> str:
        """Human readable multi-line summary for the probe console."""
        power = self.power
        if power == "UNKNOWN":
            power = f"UNKNOWN (0x{self.power_raw:02X})"
        return "\n".join(
            (
                f"power:          {power}",
                f"input:          {self.input_name} (0x{self.input_raw:02X})",
                f"dsp:            {self.dsp_mode} (0x{self.dsp_raw:02X})",
                f"mute:           {'on' if self.mute else 'off'}",
                f"clear voice:    {'on' if self.clear_voice else 'off'}",
                f"bass extension: {'on' if self.bass_extension else 'off'}",
                f"volume:         {self.volume}",
                f"subwoofer:      {self.subwoofer_level}",
                f"system flags:   {formatFrame(self.system_flags)}",
            )
        )


def parseStatusFrame(frame: bytes) -> SoundbarState:
    """Decode a status frame.

    Raises :class:`ValueError` if the frame is not a 13-byte status frame with the
    documented header and frame type. The checksum result is reported on the returned
    state instead of raising, because validating the checksum is part of what the probe
    is trying to find out.
    """
    if len(frame) != STATUS_FRAME_LENGTH:
        raise ValueError(
            f"expected {STATUS_FRAME_LENGTH} bytes, got {len(frame)}: {formatFrame(frame)}"
        )
    if not frame.startswith(HEADER):
        raise ValueError(f"bad header: {formatFrame(frame[:2])}")
    if frame[3] != STATUS_FRAME_TYPE:
        raise ValueError(f"unexpected frame type 0x{frame[3]:02X}")

    return SoundbarState(
        raw=frame,
        checksum_valid=statusChecksumValid(frame),
        power_raw=frame[4],
        input_raw=frame[5],
        dsp_raw=frame[6],
        feature_flags=frame[7],
        volume=frame[8],
        subwoofer_level=frame[9],
        system_flags=frame[10:12],
    )


class FrameReader:
    """Turn a raw RFCOMM byte stream into complete frames.

    RFCOMM is a stream, so a single ``recv()`` may return half a frame, three frames or
    a frame plus junk. This reader buffers bytes, resynchronises on the ``CC AA`` header
    and only yields frames once the length byte says they are complete.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def buffered(self) -> bytes:
        """Bytes held back while waiting for the rest of a frame."""
        return bytes(self._buffer)

    def feed(self, chunk: bytes) -> list[bytes]:
        """Add received bytes and return every frame that is now complete."""
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while (frame := self._popFrame()) is not None:
            frames.append(frame)
        return frames

    def _popFrame(self) -> bytes | None:
        index = self._buffer.find(HEADER)
        if index < 0:
            # Keep at most one byte: it may be the first half of the next header.
            if len(self._buffer) > 1:
                logger.debug(
                    "[Protocol] discarding %d non-frame byte(s)", len(self._buffer) - 1
                )
                del self._buffer[:-1]
            return None
        if index > 0:
            logger.debug("[Protocol] discarding %d byte(s) before header", index)
            del self._buffer[:index]
        if len(self._buffer) < 3:
            return None

        payload_length = self._buffer[2]
        if payload_length > MAX_PAYLOAD_LENGTH:
            # Not a plausible frame: drop the header byte and resynchronise.
            logger.debug(
                "[Protocol] implausible length 0x%02X, resynchronising", payload_length
            )
            del self._buffer[:1]
            return None

        total = 3 + payload_length + 1
        if len(self._buffer) < total:
            return None

        frame = bytes(self._buffer[:total])
        del self._buffer[:total]
        return frame
