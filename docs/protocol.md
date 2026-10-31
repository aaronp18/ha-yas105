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

Everything else — RFCOMM channel, framing, command set, response format, keepalive — is
still unknown. Do not implement against a guess.

## How to discover commands

1. Pair and trust the soundbar from the host (Bluetooth must not be claimed by another
   client; the Yamaha app or a phone holding the link will block you):

   ```bash
   bluetoothctl scan on          # note the device MAC
   bluetoothctl pair   <MAC>
   bluetoothctl trust  <MAC>
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
- Method: rfcomm bind + socat -v -x (or Android HCI snoop)
- Channel: N
- Raw:
  ...
- Interpretation (hypothesis, mark clearly):
  ...
```

## Open questions

- [ ] Which RFCOMM channel does the YAS-105 expose?
- [ ] Is the protocol line-based ASCII (many Yamaha devices are) or binary with a
      length/checksum frame?
- [ ] What are the commands (and responses) for: power on, power off, power state,
      volume up/down, absolute volume, mute on/off/toggle, input select, input state?
- [ ] Does the soundbar push state changes unsolicited, or must state be polled?
- [ ] What happens on disconnect/reconnect — does the link need re-pairing?
- [ ] Is there a keepalive or does the link idle-timeout?
