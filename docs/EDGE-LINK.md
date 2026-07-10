# Edge Link — Pi Gateway ↔ AI PC (Mac) — Build Spec

> The last hop: Raspberry Pi LoRa gateway → the AI-PC command post. Chosen strategy
> = the most robust option (bidirectional, lossless, venue-independent), because it
> also carries the **return path** (dispatch/ACK back to the victim). Status: designed
> 10 Jul 2026; Mac side building now, Pi side after.

## Why NOT BLE for this hop
This is the **connected edge** (command post in the connected town, DESIGN §0), not the
dead zone. BLE is for the disaster zone (phones). Two co-located boxes should use the
fastest reliable link. BLE Pi↔Mac = more code + flakier + MTU pain for zero benefit, and
using LAN/cable here does NOT break the offline story (the kill-switch is on the phones).

## Network (private + dedicated — never trust venue WiFi)
- **Primary: direct Ethernet** — USB-Ethernet adapter on the Mac ↔ Pi ethernet, static
  IPs (e.g. Pi 10.0.0.1 / Mac 10.0.0.2). Immune to venue client-isolation + RF congestion.
- **Fallback: Pi as WiFi AP** (`hostapd` + `dnsmasq`), Mac joins the Pi's SSID → private
  LAN, no cable. Venue WiFi is last resort (client isolation often blocks Pi→Mac silently).

## Channel — persistent WebSocket `/gateway`
Bidirectional in one connection (HTTP-POST alone can't do the return path cleanly):
- **Up:** `{type:"envelope", env:{…CONTRACT 1…}}` Pi→Mac (SOS/DELIVERED).
- **Down:** `{type:"dispatch", …}` Mac→Pi (ACCEPTED / responder instruction) → LoRa/BLE →
  victim phone. This wires the **return path** ("help is on the way").
- **ACK:** every message carries an id; receiver replies `{type:"ack", id}`. Sender keeps
  it in the durable outbox until ACKed.

## Reliability — durable + lossless
- **Durable outbox on BOTH ends** (SQLite): enqueue → send → delete only on ACK. Survives
  process restart / link blip / Mac reload → **no SOS ever lost.**
- **Idempotent:** Mac `/sos` + `/gateway` dedup by envelope id → replays are safe.
- **Priority flush on reconnect:** highest urgency first.
- **Auto-reconnect with backoff + heartbeat** (detect a dead link fast).
- **Defense-in-depth:** if the WS is down, Pi falls back to **HTTP POST /sos** for up-traffic.

## Observability
Link state + outbox depth surfaced on the dashboard and the Pi chainlog:
"gateway connected · 0 queued · last ack 40 ms". Also feeds the metrics panel (C13).

## Build tasks
**Mac (command post) — ✅ DONE + tested (10 Jul):**
- [x] `WS /gateway` — envelopes → `_ingest`; ACK by id; track the gateway connection.
- [x] `GatewayHub` downlink buffer — queue dispatches, priority flush on reconnect, ack-clears.
- [x] On responder Accept → `_dispatch_to_victims` pushes ACCEPTED down (return path).
- [x] Gateway link status on `/health` (`{connected, queued, last_ack_ms}`).
- Verified: UP ack ✓, cluster→propose(NDRF ALPHA 0.6km)→accept ✓, DOWN dispatch (ACCEPTED,
  refId, lang) ✓, health ✓.

**Pi (`pi-code/`) — module written, wiring pending:**
- [x] `uplink.py` — `DurableOutbox` (SQLite, ack-to-delete) + `EdgeUplink` WS client
      (auto-reconnect/backoff, priority flush, HTTP-POST /sos fallback, downlink handler).
- [ ] Wire into `gateway.py`: replace `_make_uplink` → `EdgeUplink.send_envelope` on the
      gateway node's `on_accept`; provide `on_dispatch(env)` that injects the ACCEPTED
      envelope into the mesh node (→ LoRa/BLE → victim phone). Needs node.py send API.
- [ ] `pip install websockets` on the Pi; config `SANKAT_UPLINK__WS=ws://<mac>:9000/gateway`
      (+ http fallback `:9000/sos`).

**Ops:**
- [ ] Direct-Ethernet static-IP (primary) OR Pi hostapd hotspot (fallback), documented.
- [ ] End-to-end: phone SOS → LoRa → Pi → WS → Mac dashboard; Accept → dispatch → victim phone.

## Wire protocol (frozen — both ends implement this)
- up:   `{"type":"envelope","id":<mid>,"env":{…CONTRACT 1 short keys…}}` → reply `{"type":"ack","id":<mid>}`
- down: `{"type":"dispatch","id":<mid>,"env":{t:"ACCEPTED",r:<sos id>,g,ln,…}}` → reply `{"type":"ack","id":<mid>}`
- `{"type":"heartbeat"}` → `{"type":"pong"}`

## Config note (existing mismatch)
Pi default `uplink.url` is `…:8000/sos`; command post runs on **9000**. Align to 9000.
