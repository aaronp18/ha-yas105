# Yamaha YAS-105 Bluetooth Control Protocol Specification

Source from Gemini converstation.

This document provides a complete technical specification for controlling and reading state feedback from the **Yamaha YAS-105 soundbar** over **Bluetooth Classic (RFCOMM / Serial Port Profile)**. It is intended for software developers and Home Assistant integration agents.

---

## 1. Connection & Protocol Overview

* **Transport:** Bluetooth Classic (RFCOMM)
* **RFCOMM Channel / Port:** `1`
* **Pairing Requirement:** Standard Bluetooth pairing must be established prior to sending RFCOMM frames (`bluetoothctl pair <MAC>`).
* **Prerequisite:** **Bluetooth Standby** MUST be enabled on the physical soundbar.
  * *Activation:* Press and hold the **BLUETOOTH STANDBY** button on the original Yamaha remote control for 3 seconds until the front LEDs flash.
  * *Why:* If disabled, the internal Bluetooth radio powers down when the unit is in standby, preventing remote wireless power-on commands.

---

## 2. Packet Structure & Checksum Protocol

Communication uses fixed-length binary frames.

### Request Packet Structure (Host → Soundbar)
$$\text{[Header: 2B]} + \text{[Length: 1B]} + \text{[Category: 1B]} + \text{[SubCmd: 1B]} + \text{[Data: 1B]} + \text{[Checksum: 1B]}$$

* **Header:** Fixed 2-byte sequence `0xCC 0xAA`.
* **Length:** Fixed byte `0x03` for standard 3-byte command payloads.
* **Checksum Calculation:** 1-byte **Two's Complement Checksum** computed over all payload bytes excluding the `0xCC 0xAA` header:

$$\text{Checksum} = (0x100 - (\text{Sum of Payload Bytes} \pmod{0x100})) \pmod{0x100}$$

---

## 3. Outbound Commands Reference Table (Host → Soundbar)

| Control Function | Hex Payload Bytes | Full Transmit Frame (with Checksum) | Notes |
| :--- | :--- | :--- | :--- |
| **Power Query** | `00 00 00` | `CC AA 03 00 00 00 2F` | Requests a full 13-byte state update frame |
| **Power ON** | `00 01 00` | `CC AA 03 00 01 00 2E` | Wakes unit from standby (requires Bluetooth Standby enabled) |
| **Power OFF (Standby)** | `00 02 00` | `CC AA 03 00 02 00 2D` | Places unit into standby mode |
| **Master Volume UP** | `00 03 00` | `CC AA 03 00 03 00 2C` | Increments master volume (+1 step) |
| **Master Volume DOWN** | `00 04 00` | `CC AA 03 00 04 00 2B` | Decrements master volume (-1 step) |
| **Mute Toggle** | `00 05 00` | `CC AA 03 00 05 00 2A` | Toggles mute state |
| **Input: TV (Optical)** | `01 01 00` | `CC AA 03 01 01 00 2D` | Switches input to Optical Digital |
| **Input: BD/DVD (Coax)** | `01 02 00` | `CC AA 03 01 02 00 2C` | Switches input to Coaxial Digital |
| **Input: ANALOG (Aux)** | `01 03 00` | `CC AA 03 01 03 00 2B` | Switches input to 3.5mm Aux |
| **Input: BLUETOOTH** | `01 04 00` | `CC AA 03 01 04 00 2A` | Switches input to Bluetooth Audio |
| **Surround: ON** | `02 01 00` | `CC AA 03 02 01 00 2C` | Enables AIR SURROUND XTREME |
| **Surround: OFF (Stereo)** | `02 00 00` | `CC AA 03 02 00 00 2D` | Sets mode to 2-Channel Stereo |
| **DSP Mode: Movie** | `02 02 00` | `CC AA 03 02 02 00 2B` | Activates Movie DSP profile |
| **DSP Mode: Music** | `02 03 00` | `CC AA 03 02 03 00 2A` | Activates Music DSP profile |
| **DSP Mode: Sports** | `02 04 00` | `CC AA 03 02 04 00 29` | Activates Sports DSP profile |
| **DSP Mode: Game** | `02 05 00` | `CC AA 03 02 05 00 28` | Activates Game DSP profile |
| **DSP Mode: TV Program** | `02 06 00` | `CC AA 03 02 06 00 27` | Activates TV Program DSP profile |
| **Clear Voice: ON** | `03 01 00` | `CC AA 03 03 01 00 2B` | Enables Dialogue Enhancement |
| **Clear Voice: OFF** | `03 00 00` | `CC AA 03 03 00 00 2C` | Disables Dialogue Enhancement |
| **Bass Extension: ON** | `04 01 00` | `CC AA 03 04 01 00 2A` | Enables Bass Enhancement |
| **Bass Extension: OFF** | `04 00 00` | `CC AA 03 04 00 00 2B` | Disables Bass Enhancement |
| **Subwoofer Vol UP** | `05 01 00` | `CC AA 03 05 01 00 29` | Increases subwoofer trim (+1 step) |
| **Subwoofer Vol DOWN** | `05 02 00` | `CC AA 03 05 02 00 28` | Decreases subwoofer trim (-1 step) |

---

## 4. Inbound Response / State Feedback Payload (Soundbar → Host)

Sending a query or changing a state triggers the soundbar to broadcast a **13-Byte Notification Frame**.

### Inbound Byte Map

| Byte Index | Byte Name | Bitmask / Value | Parsed Meaning |
| :--- | :--- | :--- | :--- |
| **0 – 1** | Header | — | Fixed `0xCC 0xAA` |
| **2** | Length | — | Fixed `0x09` (9 payload bytes follow) |
| **3** | Frame Type | — | `0x00` (Status Response Frame) |
| **4** | **Power State** | Full Byte | `0x01` = **ON**, `0x02` = **STANDBY / OFF** |
| **5** | **Input Selected** | Full Byte | `0x01` = **TV**, `0x02` = **BD/DVD**, `0x03` = **ANALOG**, `0x04` = **BLUETOOTH** |
| **6** | **Surround / DSP** | Full Byte | `0x00` = **Stereo**, `0x01` = **Surround (Movie)**, `0x02` = **Music**, `0x03` = **Sports**, `0x04` = **Game**, `0x05` = **TV Program** |
| **7** | **Feature Flags** | Bitmask `0x01` | Bit 0: `1` = **Mute ON**, `0` = **Mute OFF** |
| **7** | **Feature Flags** | Bitmask `0x02` | Bit 1: `1` = **Clear Voice ON**, `0` = **Clear Voice OFF** |
| **7** | **Feature Flags** | Bitmask `0x04` | Bit 2: `1` = **Bass Extension ON**, `0` = **Bass Extension OFF** |
| **8** | **Master Volume** | Integer Byte | Absolute master volume level |
| **9** | **Subwoofer Level**| Integer Byte | Subwoofer trim level |
| **10 – 11**| System Flags | Reserved | Hardware / audio bitstream flags |
| **12** | Checksum | — | Two's complement validation byte |

---

## 5. Python Integration Blueprint

Below is an `asyncio`-ready parsing and execution script for Home Assistant integrations or standalone control loops.

```python
import socket
import sys

BD_ADDR = "XX:XX:XX:XX:XX:XX"  # Soundbar MAC Address
RFCOMM_PORT = 1

COMMANDS = {
    "POWER_ON": bytes([0xCC, 0xAA, 0x03, 0x00, 0x01, 0x00, 0x2E]),
    "POWER_OFF": bytes([0xCC, 0xAA, 0x03, 0x00, 0x02, 0x00, 0x2D]),
    "QUERY_STATUS": bytes([0xCC, 0xAA, 0x03, 0x00, 0x00, 0x00, 0x2F]),
}


def calculate_checksum(payload: bytes) -> int:
    return (0x100 - (sum(payload) % 0x100)) % 0x100


def parse_yamaha_status(data: bytes) -> dict:
    if len(data) < 13 or data[0] != 0xCC or data[1] != 0xAA:
        raise ValueError("Invalid frame header or incomplete packet length")

    payload = data[2:12]
    if calculate_checksum(payload) != data[12]:
        raise ValueError("Checksum mismatch in received packet")

    power_raw = data[4]
    input_raw = data[5]
    dsp_raw = data[6]
    flags_raw = data[7]
    volume_raw = data[8]
    sub_volume_raw = data[9]

    INPUT_MAP = {1: "TV", 2: "BD/DVD", 3: "ANALOG", 4: "BLUETOOTH"}
    DSP_MAP = {
        0: "Stereo",
        1: "Surround",
        2: "Music",
        3: "Sports",
        4: "Game",
        5: "TV Program",
    }

    return {
        "power": "ON" if power_raw == 0x01 else "OFF",
        "input": INPUT_MAP.get(input_raw, "UNKNOWN"),
        "dsp_mode": DSP_MAP.get(dsp_raw, "UNKNOWN"),
        "mute": bool(flags_raw & 0x01),
        "clear_voice": bool(flags_raw & 0x02),
        "bass_extension": bool(flags_raw & 0x04),
        "volume": volume_raw,
        "subwoofer_level": sub_volume_raw,
    }


def send_and_read(command_bytes: bytes):
    try:
        with socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
        ) as sock:
            sock.settimeout(5.0)
            sock.connect((BD_ADDR, RFCOMM_PORT))
            sock.send(command_bytes)
            response = sock.recv(1024)
            if response:
                return parse_yamaha_status(response)
    except Exception as e:
        print(f"Bluetooth Error: {e}")
        return None
```