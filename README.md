<div align="center">
  <h1>Sankat-Mochan</h1>
  <p><strong>Autonomous Off-Grid Disaster Rescue Mesh | Snapdragon Multiverse Hackathon National Finalist</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Award-National%20Finalist-gold?style=for-the-badge&logo=qualcomm" alt="National Finalist" />
    <img src="https://img.shields.io/badge/AI-Snapdragon%20NPU%20%7C%20Whisper%20%7C%20Llama%203-orange?style=for-the-badge" alt="AI Tech Stack" />
    <img src="https://img.shields.io/badge/Platform-Android%20%7C%20Raspberry%20Pi-blue?style=for-the-badge" alt="Platforms" />
    <img src="https://github.com/Kesav2k04/Sankat-Mochan/actions/workflows/python.yml/badge.svg" alt="CI Build Status" />
  </p>
</div>

---

## 🌪️ The Problem

When floods, earthquakes, or blackouts knock out cell towers and the internet, communication is severed when it's needed most. In regions where satellite messengers are inaccessible or restricted, a localized, resilient communication fallback is critical for survival.

## 📡 The Solution

**Sankat-Mochan** is a highly resilient, offline mesh network where smartphones and localized IoT nodes autonomously form an independent radio network.

1. **Voice-First SOS & Edge Processing:** A victim simply speaks an SOS. Their phone compresses and transcribes it on-device.
2. **BLE & LoRa Mesh Relay:** The message relays phone-to-phone via **Bluetooth Low Energy (BLE)**. For kilometer-scale gaps, a **LoRa** hardware bridge spans the distance.
3. **Offline AI Command Post:** At a forward relief camp, an **offline AI command post** powered by **Snapdragon NPUs** leverages local LLMs (**Sahayak-E2B**, based on Llama 3 8B) and Whisper for urgency triage, cross-language translation, and plotting victims on a fully offline map.
4. **Responder Dispatch:** The nearest responder is automatically pinpointed and dispatched with a single tap, sending a native-language confirmation back through the mesh to reassure the victim.

The result is a **legal, subscription-free, completely offline SOS coordination system**, built to enterprise standards and capable of running multi-modal triage entirely on local edge hardware.

---

## 🧠 Sahayak-E2B: Open-Source Models

We engineered and released custom fine-tuned weights tailored for robust conversational SOS extraction on edge hardware. 

* **[Sahayak-E2B (Base Llama 3 8B Fine-tune)](https://huggingface.co/kesav2k04/sahayak-e2b):** Optimized for low-latency native English/Indic language extraction.
* **[Sahayak-E2B GGUF (Quantized for NPUs)](https://huggingface.co/kesav2k04/sahayak-e2b-gguf):** Merged and quantized (`q4_k_m`) for direct injection into Snapdragon NPU architectures via the `llama.cpp` runtime, guaranteeing 100% offline inference.

---

## 🏆 Achievements

* **National Finalist:** Snapdragon Multiverse Hackathon (Bengaluru, 11–12 July 2026).
* **Hardware Acceleration:** Native on-device inference leveraging Qualcomm's Hexagon NPU.
* **Zero-Internet Architecture:** 100% operational without external dependencies or cloud connectivity.

---

## 📁 Repository Architecture

| Component | Path | Description |
| :--- | :--- | :--- |
| **Android Mesh App** | `mesh-app/` | Native Android (Kotlin) BLE mesh app forming the T0 transport slice. Supports Victim, Responder, and Relay roles. |
| **LoRa Gateway** | `pi-code/` | Python-based gateway bridging phone ⇄ BLE ⇄ LoRa ⇄ mesh. Runs on a Raspberry Pi serving as the command post uplink. |
| **Field Node Modem** | `arduino-unoq/` | Field-side LoRa modem logic for the Arduino UNO Q, enabling the STM32 sketch to drive the Ra-02 transceiver. |
| **AI Command Post** | `command-post/` | Offline FastAPI backend receiving envelopes, executing NLP triage/translation, and serving the tactical dashboard. |
| **Edge AI Fine-Tuning**| `finetune/` | Hardware-agnostic QLoRA pipeline used to train the Sahayak-E2B edge models. |

---

## 🚀 Getting Started

### 1. Run the Mesh Application

The core Android application requires Android Studio and the Android SDK.

```bash
cd mesh-app
./gradlew assembleDebug 
```
*Note: The application must be installed on **two or more physical Android devices** (emulators do not support the required BLE peripheral/central features).*

### 2. View the Pitch Deck

The pitch deck is completely self-contained. Open it directly in any modern browser:

```bash
open deck/index.html 
```

---

## 👥 The Team

* **Krishna** - *Team Lead & Architect*
* **Isha** - *AI Research & Integration*
* **Karthi** - *Mobile Mesh Engineering*
* **Keshav** - *AI Infrastructure*
* **Siva** - *Hardware & LoRa Bridging*

---

## 📄 License

This project is open-sourced under the **[MIT License](LICENSE)** in accordance with hackathon regulations.
