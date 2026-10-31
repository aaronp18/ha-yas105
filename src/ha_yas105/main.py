import argparse
import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version

from ha_yas105.config import SystemConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Main:
    def __init__(self):

        logger.info("========================================")
        logger.info("Starting HA-YAS105 Application V" + SystemConfig.VERSION)
        logger.info("========================================")

        SystemConfig.loadFromConfigFile()

    def handleCommand(self, args: argparse.Namespace):
        match args.command:
            case "xxx":
                pass
            case _:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Playlist Generator CLI tool.")

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )

    subparsers.add_parser("help", help="Gets help")

    subparsers.add_parser("version", help="Prints the version of the program")

    return parser


def get_version() -> str:
    """Return the version."""
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

    (app or Main()).handleCommand(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
