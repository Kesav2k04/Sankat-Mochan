# Flow Simulator

A standalone React app that plays the whole Sankat-Mochan flow end to end on the
**real offline Wayanad basemap** (the same PMTiles extract the command post uses):

> victim speaks → on-device Whisper → CONTRACT 1 envelope → BLE mesh hops →
> LoRa across the kilometre gap → Pi gateway → WS `/gateway` + ACK → AI triage /
> geo-cluster / rank → nearest crew proposed → accept → **return path** back to
> the victim ("help is on the way", in their language) → crew en route → resolved.

Two modes:

- **Trace** — one Tamil SOS in real time, every hop visible, including the voice
  clip losing a chunk on the BLE tier and being repaired by NACK + `attempt=1`.
- **Surge** — the deck scenario: 40 multilingual SOS over a compressed 24 h,
  clustering, ranked dispatch, de-confliction, and a crews staffing control
  (drop to 2 and watch the queue hold + ranking pick who goes first).

Nothing is faked loosely: the envelope bytes are encoded with the real short-key
wire format and 244-byte budget, LoRa airtime comes from the Semtech formula
(SF9/BW125 → ~1.2 s for a full envelope), responder roster/coords match
`command-post/intelligence.py`, and triage output is pre-computed per
`docs/SIMULATION-DEMO.md`'s cached-playback decision.

## Run

```
npm install
npm run dev     # copies map assets from ../command-post/static, then serves
```

Map data © OpenStreetMap contributors (ODbL), rendered with MapLibre GL +
@protomaps/basemaps (BSD-3). The basemap assets are copied — not committed —
from `command-post/static/` by `scripts/copy-assets.mjs`.
