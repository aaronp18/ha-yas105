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

Early scaffold plus a protocol lab tool. The CLI (`ha-yas105`), the config loader, a first
RFCOMM transport and the interactive `probe` menu exist. The MQTT bridge and the Docker
image are not written yet.

The protocol itself is **not** confirmed: the frames implemented in
`src/ha_yas105/protocol.py` come from an AI-generated spec
([docs/yamaha_yas_105_bluetooth_protocol_spec.md](docs/yamaha_yas_105_bluetooth_protocol_spec.md))
and are still to be tested on real hardware. Protocol research, including what is verified
and what is still a guess, is tracked in [docs/protocol.md](docs/protocol.md).

## Development

Requires [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-groups     # runtime + dev dependencies (Python 3.14)
make check               # Ruff lint, format check, and pytest
uv run ha-yas105 version # run the CLI
```

Copy `config/config.example.yaml` to `config/config.yaml` for local runs; that file is
gitignored and is created automatically with defaults if it is missing.

## Probing the soundbar

`probe` is a numbered terminal menu over the (unverified) protocol frames: pick a button,
it sends the frame, prints the hex response and decodes it if it looks like a status
frame. Use it to find out which of the guessed frames the soundbar actually accepts.

```bash
uv run ha-yas105 probe --dry-run                    # only print frames; no Bluetooth needed
uv run ha-yas105 probe --address AA:BB:CC:DD:EE:FF  # real link, channel 1
uv run ha-yas105 probe --address <MAC> --channel 2 --timeout 0.5
```

Set `soundbar.bluetooth_address` and `soundbar.rfcomm_channel` in `config/config.yaml` to
skip the flags. Extra keys inside the menu: `s` poll status, `w` listen for unsolicited
frames, `r` send raw hex, `l` reprint the button list, `q` quit.

The Bluetooth link is exclusive: pair and trust the soundbar with `bluetoothctl` first, and
make sure the phone app or a stale `rfcomm bind` is not holding it. On a host without
Bluetooth (`socket.AF_BLUETOOTH` missing, e.g. plain WSL) the probe says so and only
`--dry-run` works. `sdptool browse <MAC>` shows the SPP channel to use. Findings belong in
[docs/protocol.md](docs/protocol.md), not in the code.
