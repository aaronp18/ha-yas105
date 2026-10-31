"""Interactive terminal probe for the hypothesised YAS-105 protocol.

Run ``ha-yas105 probe`` (or ``--dry-run`` to only print frames) and pick a button from
the numbered list. Each selection sends the frame from
``docs/yamaha_yas_105_bluetooth_protocol_spec.md`` and prints whatever comes back, hex
dump first, decoded state second. That is how the hypotheses in ``docs/protocol.md`` get
confirmed or thrown away.

Nothing here may be trusted as protocol fact. It is a lab tool.
"""

import logging

from ha_yas105.protocol import (
    COMMANDS,
    POWER_QUERY,
    STATUS_FRAME_LENGTH,
    STATUS_FRAME_TYPE,
    Command,
    formatFrame,
    parseHexFrame,
    parseStatusFrame,
    statusChecksumValid,
)
from ha_yas105.transport.rfcomm import TransportError

logger = logging.getLogger(__name__)

DEFAULT_LISTEN_SECONDS = 3.0

QUIT_KEYS = {"q", "quit", "exit"}
LIST_KEYS = {"l", "list", "menu"}
STATUS_KEYS = {"s", "status"}
LISTEN_KEYS = {"w", "wait", "listen"}
RAW_KEYS = {"r", "raw"}
HELP_KEYS = {"?", "h", "help"}


class DryRunTransport:
    """Transport that records frames instead of sending them.

    Same duck-typed interface as :class:`ha_yas105.transport.rfcomm.RfcommTransport`,
    used by ``ha-yas105 probe --dry-run`` and by the tests that only care about what the
    console would transmit.
    """

    isDryRun = True
    label = "dry run - frames are printed, nothing is sent over Bluetooth"

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False

    def connect(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def sendFrame(self, frame: bytes) -> None:
        self.sent.append(frame)

    def readFrames(self, _timeout: float) -> list[bytes]:
        return []


class ProtocolProbe:
    """Numbered menu that sends one protocol frame per selection."""

    def __init__(
        self,
        transport: object,
        timeout: float = 2.0,
        inputFunc=None,
        outputFunc=None,
    ) -> None:
        self.transport = transport
        self.timeout = timeout
        self.inputFunc = inputFunc or input
        self.outputFunc = outputFunc or print
        self.dryRun = bool(getattr(transport, "isDryRun", False))

    # ------------------------------------------------------------------ output

    def write(self, line: str = "") -> None:
        self.outputFunc(line)

    def printKeys(self) -> None:
        self.write("Other keys:")
        self.write("     s  query status (same frame as button 1)")
        self.write("     w  listen for frames pushed by the soundbar")
        self.write("     r  send a raw hex frame you type in")
        self.write("     l  show the button list again")
        self.write("     q  quit")

    def printMenu(self) -> None:
        self.write("")
        self.write("Buttons (type the number, or the command name):")
        group = None
        for index, command in enumerate(COMMANDS, start=1):
            if command.group != group:
                group = command.group
                self.write(f"  {group}")
            self.write(
                f"  {index:>3}  {command.label:<26} {formatFrame(command.toFrame())}"
            )
        self.write("")
        self.printKeys()
        self.write("")

    # ------------------------------------------------------------------- input

    def readLine(self, prompt: str) -> str | None:
        """Read a line, returning ``None`` on EOF or Ctrl-C."""
        try:
            return self.inputFunc(prompt)
        except EOFError, KeyboardInterrupt:
            self.write("")
            return None

    # -------------------------------------------------------------------- loop

    def run(self) -> int:
        """Connect, then serve the menu until the user quits."""
        try:
            self.transport.connect()
        except TransportError as exc:
            self.write(f"[error] {exc}")
            return 1

        self.write("")
        self.write("YAS-105 protocol probe")
        self.write(f"Link: {getattr(self.transport, 'label', self.transport)}")
        self.write(
            "Frames come from docs/yamaha_yas_105_bluetooth_protocol_spec.md and are"
            " NOT verified."
        )
        self.write("Record what actually happens in docs/protocol.md.")
        try:
            self.printMenu()
            while True:
                choice = self.readLine("probe> ")
                if choice is None or not self.handleChoice(choice):
                    break
        finally:
            self.transport.close()
        self.write("Bye.")
        return 0

    def handleChoice(self, choice: str) -> bool:
        """Act on one menu entry. Returns ``False`` when the console should stop."""
        text = choice.strip()
        if not text:
            return True

        lowered = text.lower()
        if lowered in QUIT_KEYS:
            return False
        if lowered in LIST_KEYS:
            self.printMenu()
            return True
        if lowered in STATUS_KEYS:
            self.sendCommand(POWER_QUERY)
            return True
        if lowered in LISTEN_KEYS:
            self.listen()
            return True
        if lowered in RAW_KEYS:
            self.sendRaw()
            return True
        if lowered in HELP_KEYS:
            self.printKeys()
            return True

        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(COMMANDS):
                self.sendCommand(COMMANDS[index - 1])
            else:
                self.write(f"[warn] there is no button {index}; pick 1-{len(COMMANDS)}")
            return True

        for command in COMMANDS:
            if lowered == command.key:
                self.sendCommand(command)
                return True

        self.write(f"[warn] unknown choice {text!r}; type 'l' for the button list")
        return True

    # ----------------------------------------------------------------- sending

    def sendCommand(self, command: Command) -> None:
        """Send one documented command and report the answer."""
        self.write(f"> {command.label}")
        self.exchange(command.toFrame())

    def sendRaw(self) -> None:
        """Send a frame typed in as hex, for trying formats the spec does not list."""
        answer = self.readLine("hex bytes (e.g. CC AA 03 00 00 00 2F): ")
        if answer is None or not answer.strip():
            return
        try:
            frame = parseHexFrame(answer)
        except ValueError:
            self.write(f"[error] {answer.strip()!r} is not a whole number of hex bytes")
            return
        if len(frame) < 4:
            self.write(f"[warn] {len(frame)} byte(s) is shorter than any known frame")
        self.exchange(frame)

    def listen(self) -> None:
        """Print frames the soundbar pushes without being asked."""
        answer = self.readLine(
            f"listen for how many seconds? [{DEFAULT_LISTEN_SECONDS:.0f}] "
        )
        if answer is None:
            return
        window = DEFAULT_LISTEN_SECONDS
        if answer.strip():
            try:
                window = float(answer)
            except ValueError:
                self.write(
                    f"[warn] {answer.strip()!r} is not a number, using {window:.0f}s"
                )
            else:
                window = max(0.0, window)

        if self.dryRun:
            self.write("[dry run] nothing to listen to without a Bluetooth link")
            return

        self.write(
            f"listening for {window:.1f}s (press a soundbar button to provoke a frame)"
        )
        frames = self.transport.readFrames(window)
        if not frames:
            self.write(f"  RX nothing within {window:.1f}s")
            return
        for frame in frames:
            self.reportFrame(frame)

    def exchange(self, frame: bytes) -> None:
        """Send ``frame`` and print the response frames."""
        try:
            self.transport.sendFrame(frame)
        except TransportError as exc:
            self.write(f"[error] {exc}")
            return

        self.write(f"  TX {formatFrame(frame)}")
        if self.dryRun:
            return

        frames = self.transport.readFrames(self.timeout)
        if not frames:
            self.write(f"  RX nothing within {self.timeout:.1f}s")
            self.write(
                "     hint: wrong frame or checksum, no Bluetooth Standby, or the"
            )
            self.write("     soundbar only answers state changes. Try 'w' to listen.")
            return
        for received in frames:
            self.reportFrame(received)

    def reportFrame(self, frame: bytes, prefix: str = "  RX") -> None:
        """Print one received frame as hex plus, if possible, decoded state."""
        self.write(f"{prefix} {formatFrame(frame)}  ({len(frame)} bytes)")

        if len(frame) != STATUS_FRAME_LENGTH or frame[3] != STATUS_FRAME_TYPE:
            self.write("     (not the 13-byte status frame the spec describes)")
            return

        if statusChecksumValid(frame):
            self.write("     checksum: valid")
        else:
            self.write("     checksum: INVALID with the spec's formula")

        try:
            state = parseStatusFrame(frame)
        except ValueError as exc:
            self.write(f"     could not parse: {exc}")
            return
        for line in state.describe().splitlines():
            self.write(f"     {line}")
