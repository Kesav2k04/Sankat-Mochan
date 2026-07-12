# LoRa SOS Relay Simulator

A small React app on the **real offline Wayanad basemap** (the same PMTiles
extract the command post serves). One screen, one story:

1. A **10 km danger zone** is marked over Wayanad — no cell, no internet inside.
2. **You place the LoRa modules** by clicking inside the zone (or `Auto-place`).
   Each module reaches ~5 km; the app shows which radio links close and whether
   an unbroken chain reaches the **safe-camp outpost** sitting outside the zone.
3. Press **Simulate**: a victim near the deepest module sends an SOS. The
   envelope hops module-to-module toward the outpost. LoRa is a broadcast
   medium, so **two rangers** standing in the field hear the very same
   transmissions the relay uses — ranger and outpost learn of the SOS from the
   same packets, at the same moment. The nearest ranger then heads to the victim.

Honest numbers: the SOS payload is encoded with the real CONTRACT 1 wire format
(~224 B) and each hop's on-air time comes from the Semtech LoRa airtime formula
(SF9/BW125 ≈ 1.1 s), not a made-up delay.

## Run

```
npm install
npm run dev     # copies map assets from ../backend/static, then serves
```

Map data © OpenStreetMap contributors (ODbL), rendered with MapLibre GL +
@protomaps/basemaps (BSD-3). Basemap assets are copied — not committed — from
`backend/static/` by `scripts/copy-assets.mjs`.
