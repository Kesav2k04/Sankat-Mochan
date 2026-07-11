# Arduino UNO Q — field-side of the mesh

The field radio has moved off the Raspberry Pi onto the **Arduino UNO Q**. There are two
ways to run it — pick by whether you can install Python packages on the UNO Q's Linux side.

## Which one do I use?

| | **A · Field beacon** (`field_beacon/`) | **B · On-board bridge** (`sketch/` + `field-node/`) |
| --- | --- | --- |
| Install anything on the UNO Q? | **No** — flash the `.ino` and done | Yes — Python + `bleak`/`msgpack` on the Linux side |
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
| `sketch/sketch.ino` | UNO Q **STM32** | **Option B.** The LoRa modem — drives the Ra-02 and exposes it over the **Router Bridge** (RPC), so the board's own Linux side can use it. Flashed by App Lab / `arduino-app-cli`. |
| `app.yaml`, `python/` | UNO Q (App Lab) | **Option B.** The Arduino App wrapper that flashes `sketch/` onto the MCU and keeps it alive. `python/main.py` is just a keepalive — the mesh runs in `field-node/`. |
| `field-node/` | UNO Q **Linux** | **Option B.** The same mesh code the Pi runs — BLE to phones + envelope/dedup/forwarding — talking to the modem over the Router Bridge. |
| `lora_modem/lora_modem.ino` | a *separate* Arduino | Legacy: the old serial-line modem for when the LoRa radio is on a **second** board plugged into USB (the Raspberry-Pi layout). Not used in the single-board bridge flow. |
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

# Option B — On-board bridge (full phone-Bluetooth parity, one board)

Everything runs on a **single UNO Q**: the STM32 is the LoRa modem, the Linux side runs the
field node, and the two talk over the board's **Router Bridge**.

```
victim phone ──BLE──► [UNO Q Linux: field-node (Python)] ──Router Bridge──► [UNO Q STM32: sketch.ino] ~~433 MHz~~► [Pi: gateway] ──► dashboard
victim phone ◄──BLE── [UNO Q Linux: field-node (Python)] ◄──Router Bridge── [UNO Q STM32: sketch.ino] ◄~~433 MHz~~ [Pi: gateway] ◄── dashboard
```

The UNO Q has **two brains**: the STM32 runs Arduino sketches but has **no Bluetooth**; the
Qualcomm Linux side has Bluetooth and runs Python. Crucially, the STM32 is **not** exposed
to Linux as a serial port (`/dev/ttyACM*`) — it is reached only through the always-running
`arduino-router` service on the unix socket `/var/run/arduino-router.sock`. So the modem
is an **RPC** endpoint (transport `"bridge"`), not a serial device. Same mesh code, same
behaviour as the Pi; this needs `bleak` + `requests` + `msgpack` on the Linux side.

> Have the LoRa radio on a **separate** Arduino plugged into USB instead? Then it *does*
> appear as `/dev/ttyACM0`: flash `lora_modem/lora_modem.ino` to that board and set
> `transport: "serial"` + `serial_port` in `field-node/config.json`. Everything else below
> is identical. The single-board bridge flow is the default and needs no second board.

## 1. Flash the modem (STM32) via App Lab

The modem sketch is flashed by the App framework, not the Arduino IDE (that is how Linux
reaches the on-board MCU). Copy this whole `arduino-unoq/` folder to the UNO Q
(e.g. `scp -r arduino-unoq unoq:~/`), then, on the board:

```bash
arduino-app-cli app start ~/arduino-unoq     # builds sketch/ + flashes the MCU + keeps it alive
arduino-app-cli monitor                      # optional: you should see "# LoRa modem ready"
```

Leave the App running — it keeps the MCU flashed with the modem. `python/main.py` is only a
keepalive; the mesh itself runs in the next step. Wiring is unchanged from your test —
`SS=D10, RST=D9, DIO0=D2`, radio on 3V3, antenna attached (pin list in the sketch header).

> ⚠️ The radio settings in the sketch (**433 MHz, SF7, BW 125 kHz, CR 4/5, sync 0x12,
> preamble 8, CRC on**) must match the Pi's config. They already do; if you change one,
> change it in both places or the two radios go deaf to each other.

## 2. Run the field node (Linux side)

```bash
cd ~/arduino-unoq/field-node
./run.sh check            # pre-flight: deps, Bluetooth, and the bridge modem
./run.sh                  # start the field node (waits for phones, then relays over LoRa)
./run.sh radios           # LoRa tier only, no BLE, no phones (bench check)
```

`config.json` is already set for the bridge modem — **there is no `serial_port` to edit**.
`run.sh` creates a venv in `arduino-unoq/.venv`, installs `bleak` + `requests` + `pyserial`
+ `msgpack` (all permissive), unblocks Bluetooth (needs `sudo`), pre-flights the modem, and
starts the field node. (The Pi still runs `./server.sh` as before.)

## 3. The RPC contract (for debugging)

The Linux side and the STM32 speak MessagePack-RPC over the Router Bridge. Payloads are raw
bytes (no hex doubling). The Python side is `field-node/bridge_radio.py` (a drop-in for the
SPI radio driver), using the vendored `field-node/bridge_client.py`.

| Direction | Method | Meaning |
| --- | --- | --- |
| host → MCU (call) | `lora_tx(bytes)` → `int` | transmit these bytes; returns airtime ms, or a negative error code |
| host → MCU (call) | `lora_ping()` → `str` | `"<freq> <sf> <bw> <cr> <sync-hex> <ok\|down>"` liveness + settings banner |
| MCU → host (notify) | `lora_rx(bytes, rssi, snr)` | a frame arrived (CRC already verified on the STM32) |

> Size limit: the MCU's RPC buffer is 256 B, so one `lora_tx` frame is capped at ~234 B
> (`BRIDGE_TX_SAFE_MAX` in `bridge_radio.py`). Voice chunks (217 B) and normal SOS text
> fit; oversized frames fail loud instead of corrupting. Add fragmentation if you ever
> need the full 244-byte envelope over LoRa.

## Keeping field-node/ in sync

`field-node/` is a **deployment copy** of `pi-code/` (the source of truth). If you change
the mesh code in `pi-code/`, refresh this copy before re-deploying:

```bash
./sync-from-pi-code.sh
```

`config.json` is never overwritten by the sync — it's this board's own, preconfigured for
the on-board bridge modem.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| pre-flight: `/var/run/arduino-router.sock not found` | the `arduino-router` service isn't up — is this an UNO Q with App Lab? `systemctl status arduino-router` |
| pre-flight: `modem did not answer over the Router Bridge` | flash + start the App: `arduino-app-cli app start ~/arduino-unoq`, then check the MCU with `arduino-app-cli monitor` |
| monitor banner ends `down` (not `ok`) | the Ra-02 didn't init — check SS/RST/DIO0 wiring, 3V3 power, and the antenna |
| banner shows different SF/sync | the sketch `#define`s and the config disagree — the Pi won't hear this radio; reconcile them |
| `frame NNN B exceeds the Router-Bridge single-call limit` | the envelope is larger than ~234 B — shorten it, or add fragmentation to the modem protocol |
