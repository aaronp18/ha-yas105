import tomllib
from pathlib import Path

import pytest

from ha_yas105.config import SystemConfig
from ha_yas105.main import Main, build_parser, get_version, main


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

    assert SystemConfig.config == {"settings": {"test": True}}


def test_get_version_returns_project_version():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]

    assert get_version() == project["version"]
