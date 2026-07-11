# Arduino UNO Q — field-side of the mesh

The field radio has moved off the Raspberry Pi onto the **Arduino UNO Q**. There are two
ways to run it — pick by whether you can install Python packages on the UNO Q's Linux side.

## Which one do I use?

| | **A · Field beacon** (`field_beacon/`) | **B · Serial bridge** (`lora_modem/` + `field-node/`) |
| --- | --- | --- |
| Install anything on the UNO Q? | **No** — flash the `.ino` and done | Yes — Python + `bleak`/`pyserial` on the Linux side |
| Victim's phone → UNO Q over Bluetooth? | No (UNO Q originates the SOS itself) | **Yes** — full parity with the old Pi |
| UNO Q → LoRa → Pi → dashboard? | **Yes** | **Yes** |
| Responder ACCEPT → back over LoRa? | **Yes** (lights the LED) | **Yes** (reaches the phone) |
| Use when… | you can't `pip install` on the UNO Q | the UNO Q's Linux side has the deps |

**If you cannot install packages on the UNO Q, use Option A.** The only thing it gives up
is the phone-Bluetooth-to-field hop — impossible without a BLE library, because the STM32
has no Bluetooth radio. The UNO Q instead plays the "sensor / auto-SOS field node" role,
and everything downstream (Pi triage, translate, map, responder ACCEPT, dashboard) is
identical.

## What's in here

| Path | Runs on | What it is |
| --- | --- | --- |
| `field_beacon/field_beacon.ino` | UNO Q **STM32** | **Option A.** Self-contained: builds real SOS envelopes and transmits them over LoRa; shows the ACCEPT that comes back. No Python. |
| `lora_modem/lora_modem.ino` | UNO Q **STM32** | Option B. Thin LoRa modem — drives the Ra-02 (the wiring you tested) for the Linux side to use. |
| `field-node/` | UNO Q **Linux** (via SSH) | Option B. The same mesh code the Pi runs — BLE to phones + envelope/dedup/forwarding — talking to the modem over serial. |
| `sync-from-pi-code.sh` | your dev machine | refreshes `field-node/` from the canonical `pi-code/` |

---

# Option A — Field beacon (no installs)

```
[UNO Q: field_beacon.ino]  ~~433 MHz~~►  [Pi: gateway]  ──►  dashboard
[UNO Q: field_beacon.ino]  ◄~~433 MHz~~  [Pi: gateway]  ◄──  responder taps ACCEPT
```

1. Open `field_beacon/field_beacon.ino` in the Arduino IDE.
2. Install the LoRa library (**Manage Libraries → "LoRa" by Sandeep Mistry**, MIT).
3. Upload. Open the Serial Monitor at **115200** — you'll see it fire an SOS at boot:
   ```
   # Sankat-Mochan field beacon ready
   TX SOS (boot, 181 bytes):
      {"i":"UNOQ-a1b2-1","t":"SOS","o":"UNOQ","u":5,...}
   ```
4. Fire more SOS any time: **type a character in the Serial Monitor**, press a button
   wired from `D3` to GND, or set `AUTO_SOS_SECONDS` in the sketch for a hands-free timer.
5. When a responder taps ACCEPT on the dashboard, the reply comes back over LoRa and the
   Serial Monitor prints `>>> a responder ACCEPTED <<<` and the LED flashes.

Edit the SOS content (urgency, location, message, GPS) via the `#define`s near the top of
the sketch. On the **Pi**, nothing changes — run `./server.sh` as before; it receives the
UNO Q's SOS on its gateway radio and puts it on the dashboard.

Wiring is your verified `SS=D10, RST=D9, DIO0=D2`; full pin list is in the sketch header.

> ⚠️ The radio settings (**433 MHz, SF7, BW 125 kHz, CR 4/5, sync 0x12, preamble 8, CRC
> on**) must match the Pi. They already do; change one only if you change both.

---

# Option B — Serial bridge (full phone-Bluetooth parity)

Everything the UNO Q needs is in this folder; upload *only* `arduino-unoq/` to the board.

```
victim phone ──BLE──► [UNO Q Linux: field-node (Python)] ──serial──► [UNO Q STM32: lora_modem] ~~433 MHz~~► [Pi: gateway] ──► dashboard
victim phone ◄──BLE── [UNO Q Linux: field-node (Python)] ◄──serial── [UNO Q STM32: lora_modem] ◄~~433 MHz~~ [Pi: gateway] ◄── dashboard
```

The UNO Q has **two brains**: the STM32 runs Arduino sketches but has **no Bluetooth**; the
Qualcomm Linux side has Bluetooth and runs Python. The victim's phone talks Bluetooth, so
the field logic runs on the Linux side while the radio stays on the STM32 — bridged over
the board's internal serial link. Same code as the Pi ran, same behaviour. This needs
`bleak` + `pyserial` on the Linux side (a venv, or the system python — see `field-node/`).

## 1. Flash the modem (STM32 / Arduino side)

1. Open `lora_modem/lora_modem.ino` in the Arduino IDE.
2. Install the LoRa library: **Tools → Manage Libraries → search "LoRa" by Sandeep
   Mistry → Install** (MIT-licensed — the same `<LoRa.h>` your bring-up sketch used).
3. Select the UNO Q board/port and **Upload**.
4. Open the Serial Monitor at **115200** baud. You should see:
   ```
   # LoRa modem ready
   I 433000000 7 125000 5 12
   ```
   Then **close the Serial Monitor** — only one program can hold the port, and the field
   node needs it.

Wiring is unchanged from your test — `SS=D10, RST=D9, DIO0=D2`, radio on 3V3, antenna
attached. Full pin list is in the sketch header.

> ⚠️ The radio settings in the sketch (**433 MHz, SF7, BW 125 kHz, CR 4/5, sync 0x12,
> preamble 8, CRC on**) must match the Pi's config. They already do; if you change one,
> change it in both places or the two radios go deaf to each other.

## 2. Run the field node (Linux side, over SSH)

Copy this whole `arduino-unoq/` folder to the UNO Q (e.g. `scp -r arduino-unoq
unoq:~/`), then:

```bash
cd arduino-unoq/field-node
nano config.json          # set serial_port to the modem's device (ls /dev/ttyACM* /dev/ttyUSB*)
./run.sh check            # pre-flight: deps, Bluetooth, and the serial modem
./run.sh                  # start the field node (waits for phones, then relays over LoRa)
```

`run.sh` creates a venv in `arduino-unoq/.venv`, installs `bleak` + `requests` + `pyserial`
(all permissive), unblocks Bluetooth, pre-flights the modem, and starts the field node.
That's the only command you run on the UNO Q. (The Pi still runs `./server.sh` as before.)

## 3. The serial protocol (for debugging)

The Linux side and the STM32 speak a tiny ASCII line protocol; payloads are hex so a line
can never contain a stray newline. Watch it in any serial monitor:

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

The Python side is `field-node/serial_radio.py`, a drop-in for the SPI radio driver.

## Keeping field-node/ in sync

`field-node/` is a **deployment copy** of `pi-code/` (the source of truth). If you change
the mesh code in `pi-code/`, refresh this copy before re-deploying:

```bash
./sync-from-pi-code.sh
```

`config.json` is never overwritten by the sync — it's this board's own, preconfigured for
the serial modem.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| pre-flight: `/dev/ttyACM0 not found` | `ls /dev/ttyACM* /dev/ttyUSB*` and set `radios.field.serial_port` in `field-node/config.json` |
| pre-flight: `modem did not respond` | is the sketch flashed? is the Arduino IDE Serial Monitor still open (it holds the port)? |
| modem banner shows different SF/sync | the sketch `#define`s and the config disagree — the Pi won't hear this radio; reconcile them |
| `# LoRa init FAILED` on boot | check the Ra-02 wiring (SS/RST/DIO0), 3V3 power, and the antenna |
