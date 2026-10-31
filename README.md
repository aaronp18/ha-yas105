# ha-yas105 - Home Assistant Yamaha YAS105 Soundbar Control

This repo is for creating the Home Assistant integration for the Yamaha YAS105 Soundbar Control. It is run as a docker container.

The integration uses Bluetooth Classic device via RFCOMM.

> Working with a coding agent? Read [AGENTS.md](AGENTS.md) first — it has the
> architecture map, verification commands, protocol rules and definition of done.


## AI Declaration

It's 2026, who isn't using agents. I wanted to use it to help with the boiler plate. I still think quality and arciecture are important though, so I am still being careful. But because I'm lazy, there will be bits written by AI that maybe dont make sense. Whoops


## Project Idea

- YAS-105 Soundbar is controlalble via Bluetooth Classic (RFCOMM / Serial Port Profile)
- Therefore requires a device a bluetooth device, so needs docker container that passes through.
- Comunicate with home assistant over MQTT, with MQTT discovery.
- Control volume, input, mute, power status

## Status

Early scaffold. The CLI (`ha-yas105`) and the config loader exist; the RFCOMM transport,
the MQTT bridge and the Docker image are not written yet. Protocol research is tracked in
[docs/protocol.md](docs/protocol.md).

## Development

Requires [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-groups     # runtime + dev dependencies (Python 3.14)
make check               # Ruff lint, format check, and pytest
uv run ha-yas105 version # run the CLI
```

Copy `config/config.example.yaml` to `config/config.yaml` for local runs; that file is
gitignored and is created automatically with defaults if it is missing.
