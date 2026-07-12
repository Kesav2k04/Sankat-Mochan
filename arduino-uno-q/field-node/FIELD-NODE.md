# field-node — the UNO Q's Linux-side mesh code

This is the **same code the Raspberry Pi gateway runs** (`raspberrypi/`), deployed here so the
Arduino UNO Q is fully self-contained. The Pi keeps its own copy in `raspberrypi/`.

The `.py` files, `run.sh` and `config.example.json` here are **copies of `../../raspberrypi`**.
`raspberrypi/` remains the single source of truth. If you change the mesh code there, refresh
this copy with:

```bash
../sync-from-raspberrypi.sh        # from inside arduino-uno-q/field-node
```

## How the radio is reached on the UNO Q (single-board design)

On the Raspberry Pi the LoRa modem was a **separate** Arduino plugged into USB, seen as a
serial port (`/dev/ttyACM0`). The UNO Q has **no such USB serial link to its own MCU** —
the on-board STM32 is reached over the **Router Bridge** (the always-running
`arduino-router` service, unix socket `/var/run/arduino-router.sock`). So the field radio
here is the board's own MCU, and the pieces are:

- **`../sketch/sketch.ino`** — the LoRa modem firmware for the MCU. It drives the Ra-02
  over SPI and exposes three RPCs over the Bridge: `lora_tx(bytes)->airtime_ms`,
  `lora_ping()->banner`, and a `lora_rx(bytes,rssi,snr)` notify on each received frame.
- **`bridge_radio.py`** — a drop-in for `sx127x.Radio` / `serial_radio.py` that talks to
  those RPCs. Selected by `transport: "bridge"` in `config.json`.
- **`bridge_client.py`** — the pure-Python (msgpack-only) Router-Bridge client, vendored
  from `arduino.app_utils.bridge` so this standalone process can use it without the App
  container.

`config.json` is preconfigured for this board: the `field` node, `transport: "bridge"`.
There is **no `serial_port` to edit** — the socket path defaults to the router socket.

> Size note: the MCU's RPC buffer is 256 B, so a single `lora_tx` frame is capped at
> ~234 B (`BRIDGE_TX_SAFE_MAX`). Voice chunks (217 B) and normal SOS text envelopes fit;
> oversized frames fail loud rather than corrupting. Raise it later with fragmentation if
> the full 244-byte envelope is ever needed.

## Run (two steps on the UNO Q)

```bash
# 1. Flash the MCU modem + keep it alive (App framework). Once, or after editing the sketch.
#    Point it at this arduino-uno-q/ folder (its app.yaml + sketch/ is the modem):
arduino-app-cli app start ~/arduino-uno-q

# 2. Start the field node (host process, needs Bluetooth) — from inside this folder:
./run.sh check     # pre-flight: deps, Bluetooth, and the bridge LoRa modem
./run.sh           # start the field node (waits for phones, then relays over LoRa)
./run.sh radios    # LoRa tier only, no BLE, no phones (handy for a bench check)
```

`run.sh` builds a venv in `arduino-uno-q/.venv`, installs `bleak` + `requests` +
`pyserial` + `msgpack` (all permissive-licensed), unblocks Bluetooth (needs `sudo`), and
starts the field node. Keep the App running so the MCU stays flashed with the modem; the
field node runs alongside it as a separate process.
