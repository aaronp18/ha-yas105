# Copilot / AI assistant instructions

The canonical guide for AI agents in this repository is
[`AGENTS.md`](../AGENTS.md) — read it before proposing changes.

Key points:

- Python 3.14 managed by `uv`; package code in `src/ha_yas105/`, tests in `tests/`
  (pytest), linting/formatting with Ruff. Run `make check` before finishing.
- The soundbar is reached over Bluetooth Classic (RFCOMM/SPP) and exposed to Home
  Assistant over MQTT with discovery. Tests must never use real Bluetooth, a real MQTT
  broker, or the network — fake the transport and the MQTT client.
- Configuration is loaded from `./config/config.yaml` through
  `ha_yas105.config.SystemConfig`. Use the `isolated_system_config` pytest fixture
  instead of touching the repo's config.
- Never commit `config/config.yaml`, `.env`, logs, caches, or real MAC addresses and
  MQTT credentials. Only `config/config.example.yaml` is tracked.
- Do not guess the Bluetooth protocol: `docs/protocol.md` records what has actually been
  observed on the device.
