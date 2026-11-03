import argparse
import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version

from ha_yas105.config import SystemConfig
from ha_yas105.probe import DryRunTransport, ProtocolProbe
from ha_yas105.transport.rfcomm import RfcommTransport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PROBE_TIMEOUT = 2.0


class Main:
    def __init__(self):

        SystemConfig.loadVersion()

        logger.info("========================================")
        logger.info("Starting HA-YAS105 Application V" + SystemConfig.VERSION)
        logger.info("========================================")

        SystemConfig.loadFromConfigFile()

    def handleCommand(self, args: argparse.Namespace) -> int:
        match args.command:
            case "probe":
                return self.runProbe(args)
            case _:
                return 0

    def runProbe(self, args: argparse.Namespace) -> int:
        """Open the interactive button menu against the soundbar."""
        settings = SystemConfig.getSoundbarSettings()
        address = (args.address or settings["bluetooth_address"]).strip()
        channel = (
            args.channel if args.channel is not None else settings["rfcomm_channel"]
        )
        timeout = args.timeout

        if args.dry_run:
            transport: object = DryRunTransport()
        else:
            if not address:
                logger.error(
                    "[Probe] No Bluetooth address. Set soundbar.bluetooth_address in"
                    " config/config.yaml or pass --address, or use --dry-run."
                )
                return 2
            transport = RfcommTransport(address, channel, timeout=timeout)

        return ProtocolProbe(transport, timeout=timeout).run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yamaha YAS-105 soundbar <-> Home Assistant bridge."
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )

    subparsers.add_parser("help", help="Gets help")

    subparsers.add_parser("version", help="Prints the version of the program")

    probe = subparsers.add_parser(
        "probe",
        help="Interactive terminal menu to test protocol frames on the soundbar",
        description=(
            "Interactive menu: pick a button, send the frame from the (unverified)"
            " protocol spec, print whatever comes back. Record findings in"
            " docs/protocol.md."
        ),
    )
    probe.add_argument(
        "--address",
        help="Soundbar Bluetooth MAC, overrides soundbar.bluetooth_address",
    )
    probe.add_argument(
        "--channel",
        type=int,
        help="RFCOMM channel, overrides soundbar.rfcomm_channel (default 1)",
    )
    probe.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_PROBE_TIMEOUT,
        help=f"Seconds to wait for a response frame (default {DEFAULT_PROBE_TIMEOUT})",
    )
    probe.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the frames that would be sent; no Bluetooth, no soundbar",
    )

    return parser


def get_version() -> str:
    """Return the installed package version, falling back to the source constant."""
    try:
        return metadata_version("ha-yas105")
    except PackageNotFoundError:
        return SystemConfig.VERSION


def main(argv: list[str] | None = None, app: Main | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument list, defaults to ``sys.argv[1:]``.
        app: Optional pre-built application instance (used by tests).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle side-effect-free commands before loading configuration.
    if args.command == "version":
        print(f"ha-yas105 {get_version()}")
        return 0
    if args.command == "help":
        parser.print_help()
        return 0

    # Commands that talk to the soundbar load the configuration first.
    return (app or Main()).handleCommand(args)


if __name__ == "__main__":
    raise SystemExit(main())
