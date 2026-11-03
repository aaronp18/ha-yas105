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
RFCOMM transport and the interactive `probe` menu exist. `Dockerfile` and `entrypoint.sh`
exist but are not usable end to end yet: `docker-compose.yaml` is still empty and the
entrypoint calls a `run` subcommand that the CLI does not have, and the MQTT bridge is not
written.

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

The Bluetooth link is exclusive: pair and trust the soundbar once (see
[Bluetooth pairing](#bluetooth-pairing-manual-once-automatic-after)), and make sure the
phone app or a stale `rfcomm bind` is not holding it (the YAS-105 advertises SPP, but it can
refuse RFCOMM while it is busy with an audio connection). The uv-managed
Python 3.14 used here (and in the container image) is built without the BlueZ headers, so
it has no `socket.AF_BLUETOOTH`; the transport detects that and connects through `libc`
with the Linux address-family numbers, so nothing has to be rebuilt. Only a kernel without
Bluetooth (e.g. plain WSL) has to fall back to `--dry-run`. `--timeout` also bounds the
initial connect, so raise it (e.g. `--timeout 10`) if paging the soundbar is slow.
`sdptool browse <MAC>` shows the SPP channel to use. Findings belong in
[docs/protocol.md](docs/protocol.md), not in the code.

## Bluetooth pairing: manual once, automatic after

The bond is **host state, not container state**, and pairing cannot be driven from
software: the bar only accepts a new pair while it is in pairing mode, which is entered on
the bar itself (BLUETOOTH key) or from the vendor app. So pair once on the host:

```bash
bluetoothctl scan on        # wait for "YAS-105" to appear
bluetoothctl pair   <MAC>   # while the bar is in pairing mode
bluetoothctl trust  <MAC>
bluetoothctl info   <MAC>   # expect Paired: yes / Bonded: yes / Trusted: yes
sdptool browse <MAC>        # prints the SPP (0x1101) channel for config.yaml
```

`bluetoothd` stores the link key on the host (`/var/lib/bluetooth/<adapter>/<device>/`), so
it survives reboots and container restarts; nothing needs re-pairing at startup, and a
container must never try to (it would need the bar in pairing mode to succeed).

Everything *after* the bond is automatable, and belongs in this app rather than in
`docker exec` steps: stop a stray inquiry (`Discovering: yes` competes with a connect),
assert `Trusted`, resolve the SPP channel, and open RFCOMM behind a retry/backoff loop.
`--timeout` also bounds the initial connect, so a cold page can need more than the 2 s
default. None of that preflight exists yet — `RfcommTransport` attempts one connect and
raises.

## Container

The image only contains the Python app; Bluetooth comes from the host. A working setup
needs:

- `network_mode: host` — Bluetooth sockets are kernel-global and HCI has no device node to
  pass through;
- the host D-Bus socket mounted (`/run/dbus/system_bus_socket`) so the container can reach
  the host's `bluetoothd`;
- `CAP_NET_ADMIN` / `CAP_NET_RAW` (or `privileged: true`) for the raw/HCI side. RFCOMM data
  sockets themselves do not need root: the probe reaches the kernel as a normal user;
- **no** second `bluetoothd` and **no** `/var/lib/bluetooth` bind mount in the container:
  one daemon must own `hciX`, and the bond belongs to the host.

`docker-compose.yaml` is still empty, and `entrypoint.sh` runs
`uv run /app/src/ha_yas105/main.py run` although the CLI has no `run` subcommand, so the
container does not start a bridge today. The image also ships no `bluetoothctl`, `sdptool`
or D-Bus client, so a startup preflight would need those added to the image or a switch to
the BlueZ D-Bus API.
