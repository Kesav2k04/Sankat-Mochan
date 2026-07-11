# Arduino UNO Q — field-side LoRa modem

This folder holds the code that runs on the **Arduino UNO Q** now that the field radio
has moved off the Raspberry Pi. It is the second half of the split:

```
victim phone ──BLE──► [UNO Q Linux: field node (Python)] ──serial──► [UNO Q STM32: LoRa modem] ~~433 MHz~~► [Pi: gateway] ──► dashboard
victim phone ◄──BLE── [UNO Q Linux: field node (Python)] ◄──serial── [UNO Q STM32: LoRa modem] ◄~~433 MHz~~ [Pi: gateway] ◄── dashboard
```

Nothing about the app's behaviour changes. Victim phones still connect over Bluetooth,
all roles work, and every SOS still reaches the dashboard — the only difference is that
the field radio is now on the UNO Q instead of the Pi, bridged by 433 MHz exactly as
before.

## Why two pieces on one board

The UNO Q has **two brains**:

| Brain | Runs | Our use |
| --- | --- | --- |
| STM32 (the Arduino microcontroller) | Arduino sketches | `lora_modem/` — drives the Ra-02 over SPI, the wiring you already tested |
| Qualcomm (the Linux side) | Debian, Python, **Bluetooth** | the same `pi-code` field node — BLE to phones + envelope/dedup/forwarding |

The STM32 has **no Bluetooth**, so it cannot talk to the victim's phone. The Linux side
has Bluetooth but your radio is wired to the STM32's pins. So the STM32 runs a thin
**LoRa modem** and the Linux side runs the real field logic, talking to the modem over
the board's internal serial link. Same code as the Pi ran, same behaviour.

## 1. Flash the modem (STM32 / Arduino side)

1. Open `lora_modem/lora_modem.ino` in the Arduino IDE.
2. Install the LoRa library: **Tools → Manage Libraries → search "LoRa" by Sandeep
   Mistry → Install.** (MIT-licensed — this is the same `<LoRa.h>` your bring-up sketch
   used.)
3. Select the UNO Q board/port and **Upload**.
4. Open the Serial Monitor at **115200** baud. You should see:
   ```
   # LoRa modem ready
   I 433000000 7 125000 5 12
   ```
   That `I` line is the modem reporting its settings. **Close the Serial Monitor
   afterwards** — only one program can hold the port, and the Python field node needs it.

Wiring is unchanged from your working test — `SS=D10, RST=D9, DIO0=D2`, radio on 3V3,
antenna attached. Full pin list is in the sketch header.

> ⚠️ The radio settings in the sketch (**433 MHz, SF7, BW 125 kHz, CR 4/5, sync 0x12,
> preamble 8, CRC on**) must match `pi-code/config.example.json`. They already do; if you
> change one, change it in both places or the two radios go deaf to each other.

## 2. Run the field node (Linux side)

SSH into the UNO Q's Linux side and, in the `pi-code` folder of this repo:

```bash
cp config.field.example.json config.json     # UNO Q = field node, radio over serial
# set serial_port in config.json to whatever the modem shows up as:
ls /dev/ttyACM* /dev/ttyUSB*                  # e.g. /dev/ttyACM0
./run.sh check                                # pre-flight: deps, Bluetooth, modem
./run.sh                                      # start the field node (waits for phones)
```

`run.sh` creates the venv (installing `bleak`, `requests`, `pyserial` — all permissive),
unblocks Bluetooth, pre-flights the serial modem, and starts the same gateway code the Pi
runs — just the `field` node this time.

## 3. The serial protocol (for debugging)

The Linux side and the STM32 speak a tiny ASCII line protocol; payloads are hex so a line
can never contain a stray newline. You can watch it in any serial monitor:

| Direction | Line | Meaning |
| --- | --- | --- |
| host → modem | `T <hex>` | transmit these bytes over 433 MHz |
| host → modem | `P` | ping / health check |
| modem → host | `R <hex> <rssi> <snr>` | a frame arrived (CRC already verified) |
| modem → host | `K <airtime_ms>` | the last `T` finished transmitting |
| modem → host | `E <reason>` | the last `T` failed |
| modem → host | `Y` | pong |
| modem → host | `I <freq> <sf> <bw> <cr> <sync>` | boot banner |
| modem → host | `# <text>` | human log line (ignored by the parser) |

The Python side of this is `pi-code/serial_radio.py`, a drop-in for the SPI radio driver.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| pre-flight: `/dev/ttyACM0 not found` | run `ls /dev/ttyACM* /dev/ttyUSB*` and set `radios.field.serial_port` in `config.json` |
| pre-flight: `modem did not respond` | is the sketch flashed? is the Arduino IDE Serial Monitor still open (it holds the port)? |
| modem banner shows different SF/sync | the sketch `#define`s and `pi-code` config disagree — the Pi won't hear this radio. Reconcile them. |
| `# LoRa init FAILED` on boot | check the Ra-02 wiring (SS/RST/DIO0), 3V3 power, and the antenna |
