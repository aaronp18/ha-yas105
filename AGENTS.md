# AGENTS.md

Instructions for coding agents (Cline, Claude Code, Codex, Cursor, Copilot, ...) working
in this repository. Human-facing documentation lives in [README.md](README.md).

## What this project is

A bridge between a **Yamaha YAS-105 soundbar** and **Home Assistant**.

- The soundbar has no usable IP API. It is controlled over **Bluetooth Classic**,
  Serial Port Profile / **RFCOMM** (a serial byte stream), from the device running this
  container.
- Home Assistant talks to this service over **MQTT**, using MQTT discovery so the
  entities (volume, mute, input, power) appear automatically.
- Because Bluetooth must be shared with the host, it runs as a **Docker container** with
  access to the host Bluetooth stack (`/var/run/dbus` socket, and in some setups the
  HCI device).

Status: **early scaffold with a protocol lab tool.** `src/ha_yas105` contains the CLI
entry point, the config loader, a first RFCOMM transport, a hypothesised protocol codec
(`protocol.py`) and the `probe` menu (`probe.py`). The protocol itself is **not**
confirmed, the MQTT bridge is not written, and although `Dockerfile` + `entrypoint.sh`
exist, `docker-compose.yaml` is empty and the entrypoint targets a `run` subcommand the CLI
does not have, so there is no working container yet. Do not claim a feature exists unless
the code for it is in `src/`.

## Golden rules

1. **Run `make check` before you finish.** It runs Ruff (lint + format check) and the
   full pytest suite. A change is not done while that command fails.
2. **Never touch real hardware or the network in tests.** No soundbar, no Bluetooth
   adapter, no MQTT broker. Patch the RFCOMM/socket layer and the MQTT client at the
   module where they are used; tests must pass offline on a machine without Bluetooth.
3. **Runtime config is resolved from the current working directory**
   (`./config/config.yaml`) through `ha_yas105.config.SystemConfig`. Tests must use the
   `isolated_system_config` fixture (`tests/conftest.py`) so they never read or write the
   repo's real config.
4. **Do not commit generated state or secrets:** `config/config.yaml`, `.env`, `logs/`,
   caches, `.venv/`. Only `config/config.example.yaml` is tracked. Never commit a real
   soundbar MAC address, MQTT username/password, or broker address.
5. **Match local style.** Files are `snake_case`; methods are `camelCase`
   (`loadFromConfigFile`, `addMissingConfigParameters`), matching the sibling
   `playlist-generator` project. Match the file you are editing; do not rename public
   methods without updating every caller and test.
6. **Keep `SystemConfig` authoritative.** All configuration is read through
   `SystemConfig`; do not parse YAML ad hoc in other modules. New keys go in
   `generateDefaultConfig()` **and** `config/config.example.yaml`.
7. **Python 3.14** (`.python-version`), Ruff targets `py314`, `requires-python = ">=3.14"`.
   Use modern syntax (`X | None`, `match`) as the existing code does.
8. **Do not invent the Bluetooth protocol.** If a command byte/format is not in
   [docs/protocol.md](docs/protocol.md) and not verified on the device, capture traffic
   first and record it there; do not guess and do not present guesses as facts.

## Commands

| Task | Command |
| --- | --- |
| Install deps (incl. dev) | `uv sync --all-groups` |
| Run all checks (lint + tests) | `make check` |
| Run tests | `uv run pytest` / `uv run pytest tests/test_cli.py::test_parser_accepts_version` |
| Lint | `uv run ruff check .` |
| Auto-fix lint | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Show version | `uv run ha-yas105 version` |
| Show CLI help | `uv run ha-yas105 help` |
| Probe frames offline (no Bluetooth) | `uv run ha-yas105 probe --dry-run` |
| Probe the real soundbar | `uv run ha-yas105 probe --address <MAC> --channel <N>` |
| Build/run container | `docker compose build` / `docker compose up -d` (**not functional yet**: `docker-compose.yaml` is empty, see pitfalls) |

`uv run` is preferred over activating `.venv` so commands work identically for humans
and agents. The console script `ha-yas105` maps to `ha_yas105.main:main`; the module can
also be run as `uv run python -m ha_yas105.main`.

## Architecture map

```text
src/ha_yas105/
  __init__.py          Package docstring only (no entry point; keep it that way)
  main.py              CLI: build_parser(), main(argv, app=None), Main (config bootstrap,
                       command dispatch), runProbe(), get_version()
  config.py            SystemConfig: default config, load/create/merge ./config/config.yaml,
                       getSoundbarSettings()
  protocol.py          Hypothesised frame codec: buildRequestFrame(), parseStatusFrame(),
                       FrameReader (stream -> frames), COMMANDS table, SoundbarState
  probe.py             ProtocolProbe (numbered terminal menu) + DryRunTransport
  transport/
    __init__.py        Package docstring only
    rfcomm.py          RfcommTransport + defaultSocketFactory() (Bluetooth Classic RFCOMM,
                       libc.connect() fallback when the interpreter has no AF_BLUETOOTH),
                       TransportError
tests/
  conftest.py          isolated_system_config fixture (temp CWD + patched config path)
  test_cli.py          parser, help/version short-circuit, version consistency, probe wiring
  test_config.py       defaults, merge, invalid YAML, soundbar settings
  test_protocol.py     frame building/parsing, checksum rule, FrameReader resync
  test_probe.py        menu behaviour against DryRunTransport + fake input
  test_transport.py    RfcommTransport against a fake socket/factory
config/
  config.example.yaml  Tracked schema sample (copy to config/config.yaml)
docs/
  protocol.md          Reverse-engineered RFCOMM notes: what is known and what is open
  yamaha_yas_105_bluetooth_protocol_spec.md
                       Gemini-derived protocol hypothesis. Untrusted source material;
                       `protocol.py` is a direct transcription of it.
Dockerfile             uv + python3.14-trixie-slim image, non-root `app` user,
                       ENTRYPOINT = entrypoint.sh
entrypoint.sh          `run` -> CLI dispatch (the `run` subcommand does not exist yet)
docker-compose.yaml    Empty placeholder: no service definition yet
```

Data flow (target design):

```text
Home Assistant  <--MQTT discovery/state-->  bridge (this repo)  <--RFCOMM-->  YAS-105
```

`main()` → `Main.handleCommand()` → (future) MQTT bridge → (future) RFCOMM transport →
soundbar. State read from the soundbar is published back to MQTT.

Current data flow (`probe` only):

```text
stdin (menu) -> ProtocolProbe -> transport (RfcommTransport | DryRunTransport) -> stdout
```


## Config contract

```yaml
settings:
    test: true   # scaffold placeholder, not a real feature flag

soundbar:
    bluetooth_address: ""   # MAC of the soundbar; may also be passed as --address
    rfcomm_channel: 1       # SPP channel; confirm with `sdptool browse <MAC>`
```

- `SystemConfig.getSoundbarSettings()` is the only reader of the `soundbar` section; it
  strips the address and falls back to `rfcomm_channel: 1` when the value is not an int.
- `SystemConfig.CONFIG_FILE_PATH` is `./config/config.yaml`, relative to CWD. Docker runs
  with `WORKDIR /app` and mounts `./config` at `/app/config`.
- If the file is missing, `getConfigFromFile()` calls `setDefaults()` and writes it.
- `addMissingConfigParameters()` merges new defaults into the user's file and **rewrites
  it**, so it has filesystem side effects; test it only inside a temp directory.
- Add planned keys here and to `config/config.example.yaml` when you add them in
  `generateDefaultConfig()`; keep the example credential-free.

## Bluetooth setup contract (pairing is host-owned)

- **Pairing is a one-time, manual host step, never a startup step.** The bar only accepts a
  new pair while it is in pairing mode, which is entered on the device itself or from the
  vendor app, so no code in this repo can create a bond. `bluetoothd` stores the link key
  under `/var/lib/bluetooth/<adapter>/<device>/`, so it survives reboots and container
  restarts. Startup code must assume `Bonded: yes` and must not attempt to pair.
- **Never run a second `bluetoothd` in the container, and never bind-mount
  `/var/lib/bluetooth`.** One daemon owns `hciX`; the bond belongs to the host, and the
  container has no business rewriting it.
- **Automatable at startup, and where it belongs:** assert the adapter is up, stop a stray
  inquiry (`Discovering: yes` competes with the connect), assert `Trusted`, resolve the SPP
  channel, then connect with retry/backoff. Put that behind an injected seam (subprocess
  runner or D-Bus client) in `src/ha_yas105/` and call it from `entrypoint.sh`; do not
  present `docker exec` sequences as the supported path.
- **Non-root data path is proven, raw/HCI is not.** The RFCOMM connect reaches the kernel as
  the normal app user on the test host, but the image ships no `bluetoothctl`, `sdptool` or
  D-Bus client, and the container has no `NET_ADMIN`/`NET_RAW` by default. A preflight needs
  those packages in the image (BlueZ CLI route) or the BlueZ D-Bus API (`dbus-next`), plus
  host networking, a `/run/dbus` mount and capabilities.
- `RfcommTransport` makes exactly one connect attempt bounded by `--timeout`; there is no
  retry loop yet, which is why a cold page fails after 2 s.

## Testing conventions

- Use fixtures from `tests/conftest.py`; do not hand-roll `SystemConfig` state.
- Patch dependencies at the module where they are used, not where they are defined.
- Assert observable behaviour (return values, written file contents, published MQTT
  payloads, exit codes) rather than internal call order.
- Keep tests deterministic: no sleeps, no retries, no real serial ports. Fake the
  transport with an in-memory stream or a stub class.
- The CLI must stay side-effect free for `version` and `help` (they must not construct
  `Main` or load config); `tests/test_cli.py` enforces this.

## Definition of done

- Behaviour change has a test that fails before the change and passes after.
- `make check` passes.
- `README.md`, `AGENTS.md` and `docs/protocol.md` are updated when commands, config keys,
  architecture or protocol findings change.
- Commit message follows the existing short, descriptive, versioned style
  (e.g. `V0.2.0 - Added RFCOMM transport`).

## Known pitfalls / tech debt (do not "fix" silently)

- `SystemConfig` is a process-wide static class. Avoid adding more mutable module-level
  state; prefer passing values into functions.
- `Main.handleCommand()` only dispatches `probe`. `help` and `version` are handled in
  `main()` **before** `Main` is constructed so they stay side-effect free; `Main()` does
  reload the config from disk, so tests that need a specific config must patch
  `SystemConfig.config` *after* constructing `Main`.
- The version lives in three places: `pyproject.toml`, `SystemConfig.VERSION` and the
  fallback inside `SystemConfig.loadVersion()`. They must agree. `get_version()` prefers
  installed package metadata and only falls back to the constant; the test compares
  against `pyproject.toml`.
- `SystemConfig.loadVersion()` is unused by the CLI; `main()` logs
  `SystemConfig.VERSION` directly.
- `logging.basicConfig(level=logging.INFO)` runs at import time in `main.py`. Do not add a
  second `basicConfig` call; configure loggers, not the root, elsewhere.
- `Dockerfile` and `entrypoint.sh` exist (uv + Python 3.14 slim, non-root `app` user,
  `ENTRYPOINT ["/app/entrypoint.sh"]`), but `entrypoint.sh` execs
  `uv run /app/src/ha_yas105/main.py run` while `build_parser()` only knows
  `help`/`version`/`probe`, and `docker-compose.yaml` is still 0 bytes. So there is no
  working container yet and a `run` subcommand is a prerequisite for the MQTT bridge.
  Decide between CLI-based (`bluetoothctl`/`sdptool` in the image) and D-Bus-based
  (`dbus-next` dependency) Bluetooth automation before adding packages to the image.
  Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`; `requirements.txt`
  is only a pointer and must stay that way. Run `uv lock` after editing dependencies and
  commit the lock file (CI uses `uv sync --locked`).
- `docs/protocol.md` is the only trustworthy source for the soundbar protocol. Several
  commands are still unknown; see the open questions there.
- `protocol.py` is a transcription of an AI-generated spec
  (`docs/yamaha_yas_105_bluetooth_protocol_spec.md`), **not** verified protocol. Do not
  build MQTT/HA behaviour on it until the frames are confirmed with `ha-yas105 probe` and
  recorded in `docs/protocol.md`. The spec contradicts itself about the checksum; see the
  module docstring for the rule that matches its own command table.
- `socket.AF_BLUETOOTH` is missing from some interpreter builds even on a Bluetooth host.
  The uv-managed python-build-standalone behind `.venv` and the container image is compiled
  without the BlueZ headers, so `socket.SOCK_*`/`AF_BLUETOOTH` are absent and
  `socket.connect()` rejects a Bluetooth address with `bad family` (only CPython's address
  parsing is missing; the kernel is fine). `defaultSocketFactory()` therefore falls back to
  `connectWithoutBluetoothSupport()`: it creates the socket with the Linux numbers
  (`LINUX_AF_BLUETOOTH = 31`, `LINUX_BTPROTO_RFCOMM = 3`) and calls `libc.connect()` with a
  hand-built `sockaddr_rc` from `packSockaddrRc()`. Keep `libcConnect()` as the patch seam;
  tests fake it and the `socket` module instead of needing a Bluetooth adapter. Only a
  kernel without Bluetooth (e.g. WSL) still ends in `TransportError` telling the user to
  run on Linux with BlueZ or use `--dry-run`. Do not "simplify" this back to a single
  `socket.socket(...).connect(...)` path.

## Adding a feature (recipe)

1. Add config keys to `SystemConfig.generateDefaultConfig()` and mirror them in
   `config/config.example.yaml`.
2. Implement the module in `src/ha_yas105/` (e.g. `transport/rfcomm.py`,
   `mqtt/bridge.py`) with the transport/MQTT client injected so it can be faked.
3. Wire it into `Main.handleCommand()` and add the subcommand in `build_parser()`.
4. Add `tests/test_<feature>.py` using fakes only (no Bluetooth, no broker).
5. Update `README.md`, this file, and `docs/protocol.md` if protocol behaviour changed.
