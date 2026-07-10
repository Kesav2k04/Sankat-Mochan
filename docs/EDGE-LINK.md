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
- [x] Wired into `gateway.py`: `EdgeUplink.send_envelope` on the gateway node's `on_accept`
      (VoiceChunk skipped); `on_dispatch(env)` injects the ACCEPTED envelope via
      `node.originate` → LoRa/BLE → victim phone. ws url derived from the http url.
      Merged with the teammate's voice-SOS work + pushed (merge 366716f). Compiles clean;
      needs a smoke-test on the actual Pi.
- [ ] `pip install websockets` on the Pi; set `SANKAT_UPLINK__ENABLED=true` +
      `SANKAT_UPLINK__URL=http://<mac-ip>:9000/sos` (ws `.../gateway` derived automatically).

**Ops:**
- [ ] End-to-end: phone SOS → LoRa → Pi → WS → Mac dashboard; Accept → dispatch → victim phone.

## Network setup — NO INTERNET, two independent local links
The Pi↔Mac link never touches the internet or the camp's WiFi. It's a private link
between just these two boxes. Keep BOTH ready; if one fails, switch to the other
(change one env var + restart the gateway — the durable outbox loses nothing).
The Mac is the SERVER; the Pi connects to it. The Mac command post must bind
`--host 0.0.0.0 --port 9000`, and **macOS may prompt/Firewall-block the first inbound
connection → allow it** (System Settings → Network → Firewall → allow Python/uvicorn).

### Automatic address selection
`./server.sh gateway` starts with the Mac's **mDNS/Bonjour name**, resolves every IPv4
address it advertises, rejects loopback/link-local results, prefers addresses directly
connected to the Pi, and probes `/health`. It then pins the working concrete address for
the WebSocket, avoiding the common macOS failure where the same `.local` name also
advertises VM/VPN addresses. The default is:
```
SANKAT_UPLINK__URL=http://Sivas-MacBook-Air.local:9000/sos
```
(macOS advertises this by default; the Pi resolves `.local` via avahi.) mDNS can be
flaky over some Wi-Fi APs, so `server.sh` also tries its configured raw-IP fallback. On
the Ethernet link the manual static IP `10.55.0.2` is the rock-solid option.

### Link 1 (PRIMARY) — direct Ethernet, static IPs (most reliable, zero RF)
USB-Ethernet adapter on the Mac, cable to the Pi.
- **Mac:** System Settings → Network → [USB LAN] → Configure IPv4 **Manually**:
  IP `10.55.0.2`, mask `255.255.255.0`, **no router**.
- **Pi:**
  ```
  sudo nmcli con add type ethernet ifname eth0 con-name edge ipv4.method manual \
       ipv4.addresses 10.55.0.1/24 && sudo nmcli con up edge
  export SANKAT_UPLINK__ENABLED=true SANKAT_UPLINK__URL=http://10.55.0.2:9000/sos
  ```
- **Verify (on Pi):** `curl http://10.55.0.2:9000/health` → JSON with `gateway:{...}`.

### Link 2 (FALLBACK) — Pi hosts its own WiFi hotspot (no router, no internet)
- **Pi:**
  ```
  sudo nmcli device wifi hotspot ifname wlan0 ssid sankat password rescue1234
  ```
  Pi becomes the AP at `10.42.0.1` and hands the Mac a `10.42.0.x` address.
- **Mac:** join WiFi `sankat`; find the Mac's address: `ipconfig getifaddr en0`
  (e.g. `10.42.0.240`).
- **Pi:** `export SANKAT_UPLINK__URL=http://<that-mac-ip>:9000/sos` and restart the gateway.
- **Verify (on Pi):** `curl http://<mac-ip>:9000/health`.

### Switching links
Change `SANKAT_UPLINK__URL` to the Mac's address on the active link and restart
`gateway.py`. In-flight SOS are held in the SQLite outbox and flush on reconnect, so
the switch is lossless.

### Resilience layers already in place (no code needed)
1. durable SQLite outbox (delete-only-on-ACK) — a dead link loses nothing.
2. auto-reconnect with backoff.
3. HTTP `POST /sos` fallback if the WebSocket drops while the local link is up.
4. two independent local links (Ethernet ⇄ hotspot) for "the camp has no infrastructure".
(BLE Pi↔Mac deliberately NOT built — a co-located cable/hotspot is strictly better; BLE
is a heavy last resort for a failure the above already covers.)

## Wire protocol (frozen — both ends implement this)
- up:   `{"type":"envelope","id":<mid>,"env":{…CONTRACT 1 short keys…}}` → reply `{"type":"ack","id":<mid>}`
- down: `{"type":"dispatch","id":<mid>,"env":{t:"ACCEPTED",r:<sos id>,g,ln,…}}` → reply `{"type":"ack","id":<mid>}`
- `{"type":"heartbeat"}` → `{"type":"pong"}`

## Config note (existing mismatch)
Pi default `uplink.url` is `…:8000/sos`; command post runs on **9000**. Align to 9000.
