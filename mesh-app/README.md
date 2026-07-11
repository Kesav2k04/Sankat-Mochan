# Sankat-Mochan — BLE mesh app (T0 transport slice)

One Android app, three roles (**Victim / Responder / Relay**), talking phone-to-phone
over **Bluetooth Low Energy** with no cell tower or internet. This is the T0 transport
slice from `../DESIGN.md`: a text SOS travels the mesh, the responder accepts, and the
victim's phone shows an honest native-language status ladder.

## What works now

- **Every phone is a full mesh node** — it advertises + runs a GATT server (peripheral)
  *and* scans + connects (central) at the same time. That dual role is why we went native
  Kotlin rather than React Native (no maintained RN peripheral/GATT-server library).
- **Text SOS** encoded as a compact ≤244-byte JSON envelope (fits one BLE write today,
  a 255-byte LoRa frame later).
- **Store-and-forward**: messages are deduped by id and re-broadcast once, so dropping a
  3rd "Relay" phone between victim and responder needs zero code changes.
- **Status ladder**: `Sending…` → `Message reached the control room` → `Help is on the way`.
- **Untrusted-input hygiene** (CLAUDE.md #8/#9): incoming envelopes are size/type/range
  validated, free text is stripped of control characters (no forged log lines), and
  everything is rendered as plain text only.
- **Flood / DoS protection**: dedup ids live in a capacity-bounded LRU (`BoundedIdSet`) and
  the received-SOS list is capped, so no peer can grow memory without limit; a per-peer
  token-bucket (`PeerRateLimiter`) throttles the ingress path before any decode or
  re-broadcast, so one flooding link can't be amplified across the mesh. These mirror the
  Pi gateway's own bounded-LRU + ingest-ceiling defences (`../pi-code/node.py`).

## Build & run

Prereqs: **Android Studio** (already installed via Homebrew) + **2 Android phones**
(Android 12 / API 31 or newer) with USB debugging on.

1. Open Android Studio → **Open** → select this `mesh-app/` folder.
2. Let it sync Gradle (first sync generates the Gradle wrapper and downloads SDK 35 —
   accept any SDK-install prompts). *No `./gradlew` yet — Studio's bundled Gradle handles
   the first sync, which creates the wrapper.*
3. Plug in phone #1 → pick it in the device dropdown → **Run**. Repeat for phone #2.
4. On phone #1 choose **Victim**, on phone #2 choose **Responder** (grant Bluetooth perms).
5. Tap **SEND SOS** on the victim. It appears on the responder, ranked by urgency.
6. Tap **Accept** on the responder → the victim's status flips to **Help is on the way**.

Add a 3rd phone as **Relay** and move the two endpoints out of range of each other to
demo the extra hop.

## Kill-switch demo

Turn on **airplane mode**, then re-enable **Bluetooth only** on both phones. The SOS still
crosses — nothing uses Wi-Fi or cell.

## Layout

```
app/src/main/java/com/sankatmochan/mesh/
├── MainActivity.kt          # permissions + screen routing
├── MeshViewModel.kt         # Compose ↔ mesh bridge
├── model/SosMessage.kt      # the compact envelope + validation
├── mesh/
│   ├── MeshUuids.kt         # service + characteristic UUIDs
│   ├── MessageStore.kt      # dedup + UI state flows (bounded)
│   ├── BoundedIdSet.kt      # capacity-bounded LRU dedup set (anti-DoS)
│   ├── PeerRateLimiter.kt   # per-peer token bucket (anti-flood)
│   ├── GattServerController.kt   # peripheral: advertise + GATT server
│   ├── GattScannerController.kt  # central: scan + connect + write
│   └── BleMeshService.kt    # orchestrator: dedup, forward, status ladder
└── ui/                      # RoleSelection / Victim / Responder / Relay screens

app/src/test/java/com/sankatmochan/mesh/   # JVM unit tests (see "Testing" below)
```

## Testing

Pure-JVM unit tests cover the trust-boundary and mesh logic — envelope parsing/validation,
voice framing, dedup, the DoS caps and the rate limiter. No device or emulator needed:

```
./gradlew :app:testDebugUnitTest
```

The suite is hermetic: `SosMessage` (which uses `org.json`) runs against the Apache-2.0
AOSP `android-json` — the same parser as on device — rather than Crockford's reference jar,
whose licence is disallowed by CLAUDE.md #1. See the `LICENSE FLAG` note in
`app/build.gradle.kts` about JUnit 4 (EPL-1.0, test-only) awaiting human sign-off.

## Offline map tiles (responder screen)

The responder screen pins every SOS that carries GPS coordinates on a map rendered by
osmdroid (Apache-2.0) from a **local tile archive**. Nothing is fetched at runtime —
`setUseDataConnection(false)` plus an `OfflineTileProvider` mean the app has no network
path to a tile server even if one were reachable.

No archive ships in this repo, because tiles are large and region-specific. Without one
the screen still shows coordinates, distance and bearing, and says the map is missing.

To add a map for your region:

1. Generate an `.mbtiles` archive (also accepted: `.sqlite`, `.zip`, `.gemf`) for the
   bounding box and zoom range you need. Zoom 12–17 over a city is usually tens of MB;
   check the tile provider's usage policy before bulk-downloading.
2. Install it either way:
   - **Bundled** — drop it in `app/src/main/assets/tiles/` and rebuild. It is unpacked
     into app-private storage on first launch, off the main thread.
   - **Sideloaded** — push it straight to the device, no rebuild:
     ```
     adb push region.mbtiles \
       /sdcard/Android/data/com.sankatmochan.mesh/files/osmdroid/tiles/
     ```
3. Restart the app. Both paths land in the same directory and need no storage
   permission on API 31+.

## Not built yet (next slices)

- Voice SOS over BLE (DESIGN Case A) + on-device STT.
- The AI command-post dashboard (separate PC app — the AI lane).
- LoRa bridge (hardware not yet available).
