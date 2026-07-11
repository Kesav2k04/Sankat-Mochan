# LoRa gateway — phone ⇄ phone over 433 MHz

```
phone A ──BLE──► [field node]  ══ 433 MHz ══►  [gateway node] ──BLE──► phone B
phone A ◄──BLE── [field node]  ◄══ 433 MHz ══  [gateway node] ◄──BLE── phone B
```

A phone has no LoRa radio, so it cannot "use LoRa" itself. It hands the envelope to this Pi over
Bluetooth (which still works in airplane mode once you re-enable Bluetooth), and the Pi's two
Ra-02 radios carry it across the air.

## The guarantee

`gateway.py` runs **two** `MeshNode`s that share no dedup set and no link:

```python
field   = MeshNode(links=[lora_A, ble_phone_A])
gateway = MeshNode(links=[lora_B, ble_phone_B])
```

Nothing in this process connects phone A's BLE link to phone B's. The only edge between the two
halves is the radio hop. Unplug radio B's antenna and delivery stops — that is a structural
property, not a convention. `selftest_lora.py` asserts it (scenario 6).

Why two nodes and not one: a single node holding both radios would mark an envelope id "seen" when
radio A transmitted it, and then drop its own reception on radio B as a duplicate.

## Files

| File | What it is |
| --- | --- |
| `sx127x.py` | SX1276/78 driver: init, TX, RX-continuous, CAD, per-frame RSSI/SNR. Raw `spidev` + `RPi.GPIO`. |
| `envelope.py` | CONTRACT 1 — the ≤244-byte JSON envelope. A port of `model/SosMessage.kt`, which is the source of truth. |
| `node.py` | CONTRACT 1 mesh semantics: validate → dedup → forward to every link except the source. |
| `ble_link.py` | CONTRACT 2 — BLE central (`bleak`): subscribe to notifications, write envelopes back. |
| `chainlog.py` | The two logs, and `summarise()` which answers "did this envelope really cross the air?" |
| `gateway.py` | Entry point. |
| `selftest_lora.py` | Hardware self-test, no phones needed. |
| `config.example.json` | Every tunable. Nothing is hardcoded. |

## Run

One script does everything. It creates the venv, installs deps, unblocks Bluetooth,
pre-flights the hardware, and only then starts.

```bash
cd ~/project-mesh/gateway

./run.sh          # check everything, then run the gateway (waits for phones)
./run.sh check    # pre-flight only: config, deps, SPI, Bluetooth, both radios
./run.sh test     # pre-flight + the 8-scenario hardware self-test (no phones needed)
./run.sh radios   # LoRa tier alone, no BLE
./run.sh proof    # did each envelope really cross the air?
./run.sh logs     # tail the human-readable log
```

`./run.sh` is safe to re-run and refuses to start on a broken link:

* **Pre-flight** (11 checks) reads both chips' `RegVersion`, does a write/read-back,
  pulses RST and confirms the chip reverted, and watches DIO0 rise on a CAD. Nothing
  transmits, so it is safe with or without antennas.
* **Startup probe** then sends one frame from radio A and *requires* radio B to hear it,
  before any phone is attached. If the link is dead the gateway exits with status 3
  rather than sitting there looking healthy. (Verified by detuning radio B's sync word:
  the probe correctly refuses to start.)
* **Waits for the first phone** instead of dying, then keeps scanning. A victim can
  send an SOS immediately with no responder present; responders attach whenever they
  arrive, without restarting the gateway.

Run the pieces directly if you prefer: `../.venv/bin/python {preflight,selftest_lora,gateway,chainlog}.py`.

## Configuration

`config.example.json` holds the defaults. Override by copying it to `config.json`, or per-run with
env vars — dotted path, `.` written as `__`, prefixed `SANKAT_`:

```bash
SANKAT_LOG__LEVEL=DEBUG          ../.venv/bin/python gateway.py
SANKAT_LORA__TX_POWER_DBM=17     ../.venv/bin/python gateway.py     # more range
SANKAT_LORA__SPREADING_FACTOR=12 ../.venv/bin/python gateway.py     # max range, ~30x slower
SANKAT_BLE__PEERS__FIELD=AA:BB:CC:DD:EE:FF ../.venv/bin/python gateway.py
SANKAT_UPLINK__ENABLED=true SANKAT_UPLINK__URL=http://10.148.169.50:8000/sos ../.venv/bin/python gateway.py
```

An env var that doesn't match a real config key is a hard error, so a typo can't silently do
nothing. Secrets go in env vars only, never in the JSON (project rule 2).

Radio pins live in `radios.field` / `radios.gateway`. When the UNO Q arrives, radio A moves to it
and only its transport changes — the envelope, dedup and forwarding rules are identical on both
tiers, which is the whole point of CONTRACT 1.

## Split deployment: Pi (gateway) + UNO Q (field)

Originally both Ra-02 radios sat on one Pi (`run.nodes: ["field", "gateway"]`). The field radio has
now moved to the **Arduino UNO Q**. Each board runs the same code but only its own node:

| Board | `run.nodes` | Radio transport | Setup |
| --- | --- | --- | --- |
| Raspberry Pi (relief camp) | `["gateway"]` | `spi` (radio wired to the Pi) | `cp config.gateway.example.json config.json`, then `../server.sh` as before |
| Arduino UNO Q (field) | `["field"]` | `serial` (radio on the STM32 modem) | ships as the self-contained `../arduino-unoq/` folder — that carries its own copy of this code; see below |

Each radio's `transport` decides how it is driven: `"spi"` (wired to that board's SPI) or `"serial"`
(reached over the UNO Q's STM32 LoRa modem — see `../arduino-unoq/`). The two boards are still bridged
**only** by 433 MHz, so the loop-freedom guarantee above is unchanged. The RF startup probe (which needs
both radios on one board) auto-disables when a board runs a single node; the link is then proven by live
traffic and each board's own radio watchdog.

The Pi keeps running via `../server.sh` (gateway + uplink to the dashboard). The UNO Q does **not** run
`server.sh` and does not uplink — it relays over LoRa and the Pi does the uplinking. Because only the
`arduino-unoq/` folder is uploaded to the UNO Q, that folder carries its own deployment copy of this code
in `arduino-unoq/field-node/` (kept in sync with `arduino-unoq/sync-from-pi-code.sh`; this `pi-code/` stays
the source of truth). Full UNO Q instructions: [`../arduino-unoq/README.md`](../arduino-unoq/README.md).

## Proving it went over LoRa

`logs/chain.jsonl` is append-only, one JSON row per hop event, `fsync`'d so a crash mid-demo can't
lose the evidence. For an envelope to count as LoRa-delivered, the **same payload hash** must appear
in a `LORA_TX` row on one radio and a `LORA_RX` row on a *different* radio:

```
$ ../.venv/bin/python chainlog.py
envelope         via LoRa  radio TX -> RX              RSSI     SNR
----------------------------------------------------------------------
selftest-1       YES       field -> gateway         -55 dBm 9.25 dB
selftest-ack-1   YES       gateway -> field         -52 dBm 9.75 dB
selftest-2       NO        no LORA_RX                     -       -
```

Matching on envelope id alone would also be satisfied by an in-process hand-off. Matching the
sha256 of the exact bytes **across two distinct radios**, alongside an RSSI and SNR read out of the
receiving chip's own demodulator registers, cannot be. There is no code path that fabricates those
numbers, and no way to obtain them without a frame arriving over RF.

`selftest-2` above is the negative control: the same envelope, transmitted with radio B asleep.

Event types: `START`, `BLE_RX`, `LORA_TX`, `LORA_RX`, `BLE_TX`, `DROP`, `PEER`, `UPLINK`.
Every `DROP` carries a `reason` (`crc_error`, `malformed`, `duplicate`, `mtu_too_small`,
`send_failed`, `tx_failed`).

Trace one message end to end:

```bash
grep '"msg_id":"a3f9-4"' logs/chain.jsonl | ../.venv/bin/python -m json.tool --json-lines
```

## Radio settings and range

Defaults are `433.0 MHz, SF7, BW125k, CR4/5, 5 dBm` — deliberately low power, because in testing the
two antennas sit inches apart. **A 244-byte frame at SF7 takes ~310 ms on air.**

For real distance raise `tx_power_dbm` (max 20) and `spreading_factor` (max 12). SF12 buys roughly
2.5× the range of SF7 and costs ~30× the airtime; at SF12 a full envelope is several seconds on air,
so send fewer of them. Both radios must agree on frequency, SF, BW, CR and sync word or they will
not hear each other at all.

⚠️ **Never transmit without an antenna** — the PA reflects into itself and degrades. And confirm
433 MHz ISM use is permitted in your region before running anything sustained.

## Untrusted input

Every envelope off BLE or the air is untrusted (project rule 8). `envelope.decode()` returns `None`
— meaning "drop it" — for anything oversized, non-UTF-8, non-JSON, non-object, missing `i`/`o`, or
carrying an unknown `t`. Numeric fields are clamped (`u`→1..5, `h`→0..15, coords to valid ranges,
non-finite coords dropped) and strings are length-capped. No field is ever interpreted as a command.

## Dependencies

`bleak` (MIT), `requests` (Apache-2.0) on every board. Then per transport: the Pi's SPI radios use
`spidev` (MIT) + `RPi.GPIO` (MIT) — from the system packages, hence the `--system-site-packages` venv;
the UNO Q's serial modem uses `pyserial` (BSD-3-Clause). `gpio_compat.py` selects `RPi.GPIO`/`lgpio`
(Unlicense) as available. All permissive, per rule 1.
