# YAS-105 protocol notes

Lab notebook for the soundbar control protocol. This file is the **only** trusted source
for protocol facts in this repo. Anything not recorded here is unknown.

Rule: record what you observed, how you observed it, and when. Never write a command
here because it "seems likely" — if it is a hypothesis, put it under
[Open questions](#open-questions).

## Confirmed

| Fact | Evidence |
| --- | --- |
| Control link is Bluetooth Classic Serial Port Profile (RFCOMM), i.e. a byte stream, not BLE GATT and not IP. | Project premise in `README.md`; the soundbar advertises itself over Classic Bluetooth. |
| The container therefore needs access to the host Bluetooth stack (D-Bus) and to the paired device. | Requirement, see `AGENTS.md`. |
| The soundbar advertises Serial Port Profile (UUID `0x1101`) next to A2DP/Audio Sink. | `bluetoothctl info <MAC>` on the Linux host, 2026-10-31: UUID `00001101-0000-1000-8000-00805f9b34fb` listed. The channel number is still unknown. |

Everything else — RFCOMM channel, framing, command set, response format, keepalive — is
still unknown. Do not implement against a guess.

## Link prerequisites (host side)

Not frame bytes, but the probe cannot produce protocol data until these hold. They live
here because "the connect timed out" is easy to misread as a protocol or interpreter
problem.

| Fact | Evidence |
| --- | --- |
| While it is unbonded, the bar does not answer SDP/RFCOMM: `sdptool browse <MAC>` prints only `Browsing <MAC> ...` and returns nothing for 45 s, and `ha-yas105 probe` ends in `timed out connecting to <MAC> on RFCOMM channel 1 after 2s`. | 2026-10-31, host `hci0` (`comet`), BlueZ 5.72; `bluetoothctl info`: `Paired: no`, `Bonded: no`, `Trusted: no`, `Connected: no`. |
| That silence is peer-side, not a local permission problem: the control test `sdptool browse 11:22:33:44:55:66` (no such device) fails immediately with `Failed to connect to SDP server ... Host is down`. Raw SDP therefore works from an unprivileged session on this host (no file caps on the BlueZ tools, user not in the `bluetooth` group). | Same session, 2026-10-31. |
| Pairing is a one-time manual step: the bar only accepts a new pair while it is in pairing mode, which is entered on the bar itself (BLUETOOTH key) or from the vendor app. No container or Python startup code can open that window, so automation has to treat pairing as already done. | Operational constraint. |
| The bond is host state: `bluetoothd` keeps the link key under `/var/lib/bluetooth/<adapter>/<device>/` (root-only), so it survives reboots and container restarts. A container must not mount/rewrite that directory and must not run a second `bluetoothd`; one daemon owns `hciX`. | BlueZ storage layout; `/var/lib/bluetooth` is not readable by the app user on the test host. |
| An active inquiry competes with the connect: `hciconfig -a` showed `Discovering: yes` while the probe timed out. Stop it (`bluetoothctl scan off`) before connecting. | 2026-10-31. |
| The bar may not even be known to the adapter yet: `bluetoothctl info <MAC>` answered `Device ... not available` and `bluetoothctl devices` was empty until `bluetoothctl scan on` had run once. | 2026-10-31. |

Not yet shown: whether `Trusted: yes` is required in addition to `Bonded: yes`, whether the
bar needs an authenticated/encrypted SPP link, and whether it accepts SPP while an A2DP
link is up. See [Open questions](#open-questions).

## Unverified hypothesis: the AI-generated spec

`docs/yamaha_yas_105_bluetooth_protocol_spec.md` is a protocol description produced by an
AI conversation. Nothing in it has been observed on a device. It is kept because it is a
**testable** starting point, and `src/ha_yas105/protocol.py` is a literal transcription of
it so the probe can send exactly what it claims. Treat the whole section below as a
hypothesis with a status of "not yet tried".

| Hypothesis (from the spec) | Status |
| --- | --- |
| Frame format `CC AA <len> <payload...> <checksum>`, header `CC AA` in both directions | Untested |
| Request frame: `len = 0x03`, payload = `category subcommand data` | Untested |
| Request checksum: two's complement of the payload sum (see contradiction below) | Contradicted by the spec's own table |
| Status frame: `CC AA 09 00 <power> <input> <dsp> <flags> <volume> <subwoofer> <sys[2]> <checksum>` (13 bytes) | Untested |
| Input codes: `01` TV/optical, `02` BD/DVD, `03` ANALOG, `04` BLUETOOTH | Untested |
| DSP codes: `01` Surround, `02` Movie, `03` Music, `04` Sports, `05` Game, `06` TV Program | Untested |
| Volume up/down are relative commands; no absolute-volume frame is specified | Untested |
| SPP channel 1 | Untested — verify with `sdptool browse <MAC>` |

### The spec contradicts itself about the checksum

The prose says

```text
checksum = (0x100 - (sum of payload bytes % 0x100)) % 0x100   # two's complement
```

Applied to `CC AA 03 00 01 00 ??` (power on) that gives `FC`. The command table in the same
document prints `2E` for that frame. All 23 rows of the table satisfy

```text
checksum = (0x2F - (category + subcommand + data)) & 0xFF
```

i.e. `0x2F - sum(payload)`, not `0x100 - sum(payload)`. `protocol.requestChecksum()`
implements the rule that reproduces the table, and
`tests/test_protocol.py::test_checksum_rule_conflicts_with_spec_prose` pins the conflict.
Which one the soundbar accepts is unknown: try both with the probe's raw (`r`) input.

## Probe tool

`ha-yas105 probe` is the fast way to check these hypotheses without wiring up `rfcomm` +
`socat` by hand. It is a numbered menu over the 23 documented buttons plus a raw-hex option.

```bash
uv run ha-yas105 probe --dry-run                       # print frames only, no Bluetooth
uv run ha-yas105 probe --address AA:BB:CC:DD:EE:FF     # channel 1, 2s timeout
uv run ha-yas105 probe --address <MAC> --channel 2 --timeout 0.5
```

`--address`/`--channel` override `soundbar.bluetooth_address` / `soundbar.rfcomm_channel`
from `config/config.yaml`. Keys: a number or command name sends that frame, `s` polls
status, `w` listens for unsolicited frames for N seconds, `r` sends hex you type, `l`
reprints the menu, `q` quits.

Read the output like this:

- `TX …` — what was sent. Compare it with the spec table.
- `RX …  (N bytes)` — what came back. `(not the 13-byte status frame the spec describes)`
  means the framing guess is wrong; note the real bytes here instead of adjusting the code.
- `checksum: valid` / `checksum: INVALID with the spec's formula` — tells you whether the
  status frame checksum matches the two's-complement prose formula (still untested).

Pair and trust the soundbar first (`bluetoothctl`, see
[Link prerequisites](#link-prerequisites-host-side)), and make sure nothing else holds the
link: an open Yamaha app session or a running `rfcomm bind` will make `connect` fail with
"device or resource busy". Copy the raw `TX`/`RX` lines into the capture log below.
`--timeout` also bounds the initial connect, so use a larger value if paging the soundbar
takes longer than 2 s. On a host whose Python was built without BlueZ headers (the uv
Python used here) the transport connects through `libc` instead of `socket.AF_BLUETOOTH`;
that is a transport detail, not protocol behaviour.

## How to discover commands

1. Pair and trust the soundbar from the host, once. The bar only accepts a new pair while it
   is in pairing mode, so this step needs a hand on the device; the bond is then kept by the
   host (see [Link prerequisites](#link-prerequisites-host-side)) and does not have to be
   repeated for every container start. Bluetooth must also not be claimed by another client:
   the Yamaha app or a phone holding the link will block you.

   ```bash
   bluetoothctl scan on          # note the device MAC
   bluetoothctl pair   <MAC>
   bluetoothctl trust  <MAC>
   bluetoothctl scan off         # an active inquiry competes with the connect
   bluetoothctl connect <MAC>
   ```

2. Find the SPP channel:

   ```bash
   sdptool browse <MAC>          # look for "Serial Port" / 0x1101 and its channel
   ```

3. Bind it to a local serial device and sniff both directions while you press buttons on
   the remote:

   ```bash
   sudo rfcomm bind 0 <MAC> 1    # 1 = channel from sdptool
   socat -v -x /dev/rfcomm0 -
   ```

   `socat -v -x` prints a timestamped hex dump of traffic in both directions, which is
   exactly what belongs in the "Capture log" section below. (RFCOMM is a stream, so baud
   rate/parity settings do not apply.)

4. If the link is encrypted/authenticated in a way a plain `rfcomm` bind cannot use,
   capture an Android HCI snoop log (`btsnoop_hci.log`) from a phone running the vendor
   app and extract the RFCOMM payloads instead.

## Capture log

Add one entry per session, newest first:

```text
## YYYY-MM-DD - <what you did>
- Method: ha-yas105 probe (or rfcomm bind + socat -v -x, or Android HCI snoop)
- Channel: N
- Raw:
  ...
- Interpretation (hypothesis, mark clearly):
  ...
```

## 2026-10-31 - first connection attempt with ha-yas105 probe (Linux host, BlueZ 5.72)

- Method: `ha-yas105 probe` (connect only, no frame sent), plus `bluetoothctl info <MAC>`
  and `sdptool browse <MAC>`
- Channel: 1 (from the hypothesis, not confirmed)
- Raw: no frames captured. The RFCOMM connect did not complete within 2 s or 12 s, and
  `sdptool browse` failed with `Failed to connect to SDP server ... Software caused
  connection abort`.
- `bluetoothctl info <MAC>` at the same time: `Paired: no`, `Bonded: no`, `Connected: yes`
  (A2DP), SPP UUID `0x1101` advertised.
- Interpretation (hypothesis, mark clearly): the soundbar was holding an audio link and is
  not bonded, so it did not answer the SPP connect. Pair + trust it, disconnect the audio
  source, and retry with `--timeout 10` before drawing any protocol conclusion.
- Follow-up on the same day, same host (adapter `hci0`, name `comet`, BlueZ 5.72):
  - `bluetoothctl info <MAC>` answered `Device ... not available` and `bluetoothctl devices`
    was empty: the soundbar had never been seen by this adapter, so it is not in the BlueZ
    cache. Only after `bluetoothctl --timeout 12 scan on` did it show up as
    `YAS-105  Yamaha`, class `0x00240414`. State at that point: `Paired: no`,
    `Bonded: no`, `Trusted: no`, `Connected: no`.
  - `sdptool browse <MAC>` still printed only `Browsing <MAC> ...` and returned no records
    after 45 s, i.e. the remote SDP/RFCOMM connect is not answered at all. So the probe's
    `timed out connecting ... after 2s` is a peer-side/bonding problem, **not** an
    interpreter problem: the `libc` connect fallback used on builds without
    `socket.AF_BLUETOOTH` does reach the kernel (a missing socket family would fail
    immediately with "Bluetooth RFCOMM sockets are unavailable" instead of timing out).
  - Control test for the silence: `sdptool browse 11:22:33:44:55:66` (no such device)
    returned `Failed to connect to SDP server on 11:22:33:44:55:66: Host is down` at once,
    so the local SDP path works and only the bar fails to answer. `hciconfig -a` during the
    attempts: `UP RUNNING`, `Discovering: yes`.
  - Still no frames captured, so no protocol conclusion; channel remains unknown.

## Open questions

Answer these with `ha-yas105 probe` and write the result into the capture log above; move
a row from the hypothesis table into [Confirmed](#confirmed) only when the frame was
actually seen working on a device.

- [ ] Which RFCOMM channel does the YAS-105 expose? (`sdptool browse <MAC>` — it returns
      nothing until the host is bonded, so pair first)
- [ ] Does the bar require `Bonded: yes` (authenticated/encrypted link), or does it accept
      an anonymous RFCOMM connect once nothing else holds it? Does `Trusted: yes` add
      anything on top of `Bonded: yes`?
- [ ] Which pairing flavour does the bar use — SSP "Just Works", or legacy PIN (and which
      PIN)? This decides whether unattended pairing could ever be scripted.
- [ ] Does the bar accept the SPP link while an A2DP connection is up, or is it one
      connection at a time?
- [ ] Is the protocol line-based ASCII (many Yamaha devices are) or binary with a
      length/checksum frame (`CC AA …`)?
- [ ] Does the soundbar accept `CC AA 03 00 01 00 2E` (spec table checksum) or the
      two's-complement `FC` variant — or neither?
- [ ] Do the 23 documented button frames actually do what the spec says?
- [ ] What is the real status/response frame: 13 bytes as claimed, or something else?
- [ ] Is the status checksum two's complement of the payload, or the `0x2F - sum` rule of
      the request frames, or something else again?
- [ ] Is there an absolute volume command (needed for `media_player.volume_set`), or only
      up/down?
- [ ] Does the soundbar push state changes unsolicited, or must state be polled?
- [ ] What happens on disconnect/reconnect — does the link need re-pairing?
- [ ] Is there a keepalive or does the link idle-timeout?
- [ ] Does the device refuse commands in Bluetooth standby, and which frame wakes it?
