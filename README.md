# Sankat-Mochan — Off-Grid Disaster Rescue Mesh

> When floods, quakes, or blackouts knock out cell towers and the internet, phones and small
> IoT nodes form their own radio network to get SOS calls out — no towers, no internet, and
> nothing leaving the mesh. An offline AI command post triages, translates, and dispatches.
>
> Built for the **Snapdragon Multiverse Hackathon**, Bengaluru (11–12 July 2026).

---

## What this is

A victim just **speaks** an SOS. Their phone transcribes and compresses it on-device, relays it
**phone-to-phone over Bluetooth LE**, and a **LoRa** radio bridges the kilometre gaps no phone can.
At a forward relief camp, an **offline AI command post** (Snapdragon NPU: Whisper + Qwen3-4B)
triages urgency, translates between Indian languages, plots victims on an offline map, and dispatches
the nearest responder — who accepts with one tap, and the victim hears, in their own language, that
help is on the way.

The through-line: **legal, subscription-free, offline SOS coordination for India**, where satellite
messengers are illegal and cell networks fail within hours of a disaster.

## Repository layout

| Path | What's inside |
| --- | --- |
| `mesh-app/` | **Native Android (Kotlin) BLE mesh app** — the working T0 transport slice. Victim / Responder / Relay roles; every phone is a full mesh node (GATT server + scanner); store-and-forward; native-language status ladder. |
| `deck/` | The pitch **presentation** (`deck/index.html`) — a self-contained HTML deck; open in any browser. |
| `docs/planning/` | Architecture, build plan, demo/stage scripts, prep plan, and the team source-of-truth doc. |
| `docs/research/` | Fact-checked disaster evidence, model/AI-stack research, competitive analysis, and critiques. |
| `docs/reference/` | The official Qualcomm event guide (PDF). |
| `CLAUDE.md` / `AGENTS.md` | AI-tool usage rules for this repo (permissive-license deps only, no secrets, prompt-injection discipline, untrusted-input validation). |

## Team

| Member | Email |
| --- | --- |
| Krishna (lead) | _TODO_ |
| Isha | _TODO_ |
| Karthi | _TODO_ |
| Keshav | _TODO_ |
| Siva | _TODO_ |

> **Note:** the official hackathon submission requires the full name **and email** of every member in
> the README. Fill the emails above before submitting.

## Run the mesh app

Requires Android Studio + the Android SDK.

```bash
cd mesh-app
./gradlew assembleDebug          # build the debug APK
# or open the folder in Android Studio and Run on 2+ physical Android devices
```

Install on **two or more physical phones** (BLE peripheral/central needs real hardware, not an
emulator). Pick a role on each (Victim / Responder / Relay), send an SOS from the Victim, and watch
it hop the mesh and the status ladder advance. See `mesh-app/README.md` for details.

## View the deck

```bash
open deck/index.html            # macOS — or open the file in any browser
```

## License

[MIT](LICENSE). All code is open source, per hackathon rules.

---

*This is the team's private working repo (includes internal strategy/research under `docs/`).
The official hackathon submission must be a **public** repo — when you create it, publish only the
code, `deck/`, and a clean README, and leave the internal strategy/critique docs out.*
