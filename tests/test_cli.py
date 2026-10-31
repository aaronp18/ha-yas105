import tomllib
from pathlib import Path

import pytest

from ha_yas105.config import SystemConfig
from ha_yas105.main import DEFAULT_PROBE_TIMEOUT, Main, build_parser, get_version, main


def test_parser_accepts_version():
    args = build_parser().parse_args(["version"])

    assert args.command == "version"


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_version_does_not_load_config(capsys, monkeypatch):
    def fail():
        raise AssertionError("Main must not be constructed for the version command")

    monkeypatch.setattr("ha_yas105.main.Main", fail)

    assert main(["version"]) == 0
    assert "ha-yas105" in capsys.readouterr().out


def test_help_prints_usage_without_loading_config(capsys, monkeypatch):
    def fail():
        raise AssertionError("Main must not be constructed for the help command")

    monkeypatch.setattr("ha_yas105.main.Main", fail)

    assert main(["help"]) == 0
    assert "usage:" in capsys.readouterr().out


def test_main_loads_config_on_construction(isolated_system_config):
    Main()

    assert SystemConfig.config["settings"] == {"test": True}
    assert SystemConfig.config["soundbar"] == {
        "bluetooth_address": "",
        "rfcomm_channel": 1,
    }


def test_parser_accepts_probe_defaults():
    args = build_parser().parse_args(["probe"])

    assert args.command == "probe"
    assert args.address is None
    assert args.channel is None
    assert args.timeout == DEFAULT_PROBE_TIMEOUT
    assert args.dry_run is False


def test_probe_without_address_asks_for_one(isolated_system_config):
    args = build_parser().parse_args(["probe"])

    assert Main().runProbe(args) == 2


def test_probe_dry_run_never_opens_bluetooth(isolated_system_config, monkeypatch):
    captured = {}

    class FakeProbe:
        def __init__(self, transport, timeout):
            captured["transport"] = transport
            captured["timeout"] = timeout

        def run(self):
            return 0

    monkeypatch.setattr("ha_yas105.main.ProtocolProbe", FakeProbe)

    args = build_parser().parse_args(["probe", "--dry-run"])

    assert Main().runProbe(args) == 0
    assert captured["transport"].isDryRun is True
    assert captured["timeout"] == DEFAULT_PROBE_TIMEOUT


def test_probe_uses_command_line_overrides(isolated_system_config, monkeypatch):
    captured = {}

    class FakeTransport:
        def __init__(self, address, channel, timeout):
            captured.update(address=address, channel=channel, timeout=timeout)

    class FakeProbe:
        def __init__(self, transport, timeout):
            self.transport = transport

        def run(self):
            return 0

    monkeypatch.setattr("ha_yas105.main.RfcommTransport", FakeTransport)
    monkeypatch.setattr("ha_yas105.main.ProtocolProbe", FakeProbe)

    args = build_parser().parse_args(
        [
            "probe",
            "--address",
            "AA:BB:CC:DD:EE:FF",
            "--channel",
            "3",
            "--timeout",
            "0.5",
        ]
    )

    assert Main().runProbe(args) == 0
    assert captured == {
        "address": "AA:BB:CC:DD:EE:FF",
        "channel": 3,
        "timeout": 0.5,
    }


def test_probe_falls_back_to_the_configured_address(
    isolated_system_config, monkeypatch
):
    captured = {}

    class FakeTransport:
        def __init__(self, address, channel, timeout):
            captured.update(address=address, channel=channel, timeout=timeout)

    class FakeProbe:
        def __init__(self, transport, timeout):
            self.transport = transport

        def run(self):
            return 0

    monkeypatch.setattr("ha_yas105.main.RfcommTransport", FakeTransport)
    monkeypatch.setattr("ha_yas105.main.ProtocolProbe", FakeProbe)

    app = Main()
    # Set the config *after* construction: Main() reloads it from disk.
    monkeypatch.setattr(
        SystemConfig,
        "config",
        {
            "settings": {"test": True},
            "soundbar": {
                "bluetooth_address": "AA:BB:CC:DD:EE:FF",
                "rfcomm_channel": 4,
            },
        },
    )

    assert app.runProbe(build_parser().parse_args(["probe"])) == 0
    assert captured["address"] == "AA:BB:CC:DD:EE:FF"
    assert captured["channel"] == 4


def test_get_version_returns_project_version():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]

    assert get_version() == project["version"]
