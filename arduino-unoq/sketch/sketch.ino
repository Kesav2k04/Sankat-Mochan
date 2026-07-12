/*
 * Sankat-Mochan — field-side LoRa modem for the Arduino UNO Q (STM32 / Arduino side)
 * =================================================================================
 *
 * SINGLE-BOARD PORT.  The original modem (see ../lora_modem/lora_modem.ino) spoke an
 * ASCII line protocol over a USB serial port, because the field node ran on a Raspberry
 * Pi and the modem was a *separate* Arduino plugged into it. On the UNO Q there is no
 * such USB serial link to the on-board MCU — the MCU is reached over the Router Bridge.
 * So this sketch does the same job (a transparent 433 MHz LoRa modem) but exposes it as
 * three RPC endpoints over the Bridge instead of a serial line:
 *
 *       victim phone --BLE--> [UNO Q Linux: field node] --Router Bridge--> [THIS SKETCH]
 *                                                                              ~~433 MHz~~>  Pi gateway --> dashboard
 *
 * RPC CONTRACT  (payloads are raw bytes = MessagePack bin; no hex, so a full frame fits)
 *   HOST -> MCU (call):
 *     lora_tx(bin payload)  -> int   transmit the bytes; returns airtime in ms,
 *                                    or a NEGATIVE error code (see TX_ERR_* below).
 *     lora_ping()           -> str   liveness + active settings banner:
 *                                    "<freq> <sf> <bw> <cr> <sync-hex> <ok|down>"
 *   MCU -> HOST (notify):
 *     lora_rx(bin payload, int rssi, float snr)   a CRC-good frame arrived off the air.
 *
 * SIZE NOTE.  The MCU-side RPC request buffer is DEFAULT_RPC_BUFFER_SIZE (256 B). A
 * received/oversized RPC is *cleanly rejected* by RPClite (never truncated), so the
 * host's lora_tx call simply fails rather than corrupting a frame. In practice every
 * SOS text envelope and every 217-byte voice chunk fits; the host guards the size too.
 *
 * RADIO LIBRARY  arduino-LoRa by Sandeep Mistry — MIT. Declared in sketch.yaml.
 *
 * WIRING (the pins already verified on this board: SS=10, RST=9, DIO0=2; HW SPI D11-13).
 *
 * !! SETTINGS BELOW MUST MATCH pi-code/config.example.json (the "lora" block) !!
 *    433 MHz, SF7, BW 125 kHz, coding rate 4/5, sync word 0x12, preamble 8, CRC on.
 */

#include <SPI.h>
#include <LoRa.h>
#include <Arduino_RouterBridge.h>

// --- pins (as verified on this board) ---------------------------------------
#define SS_PIN    10
#define RST_PIN    9
#define DIO0_PIN   2

// --- radio settings: keep in lock-step with pi-code/config.example.json ------
#define LORA_FREQ_HZ   433000000L   // frequency_hz
#define LORA_SF        7            // spreading_factor
#define LORA_BW_HZ     125000L      // bandwidth_hz
#define LORA_CR4       5            // coding_rate (4/5)
#define LORA_TX_POWER  17           // tx_power_dbm (PA_BOOST) — 1 km target; SX1278 max before the +20 dBm PA_DAC mode
#define LORA_SYNC      0x12         // sync_word (18 decimal in the JSON)
#define LORA_PREAMBLE  8            // preamble_len

#define MAX_PAYLOAD    255          // matches lora.max_payload

// Negative return codes from lora_tx (the host treats any value < 0 as failure).
#define TX_ERR_RADIO_DOWN  (-1)     // radio never initialised
#define TX_ERR_BAD_LEN     (-2)     // empty or > MAX_PAYLOAD
#define TX_ERR_RADIO_BUSY  (-3)     // could not enter TX (beginPacket returned 0)

static bool radio_ok = false;

// --- radio bring-up ----------------------------------------------------------
static void applyRadioSettings() {
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW_HZ);
  LoRa.setCodingRate4(LORA_CR4);
  LoRa.setPreambleLength(LORA_PREAMBLE);
  LoRa.setSyncWord(LORA_SYNC);
  LoRa.setTxPower(LORA_TX_POWER);   // PA_BOOST pin, like the Pi driver
  LoRa.enableCrc();                 // config crc:true → lib drops CRC-bad frames on RX
}

static bool radioBegin() {
  LoRa.setPins(SS_PIN, RST_PIN, DIO0_PIN);
  if (!LoRa.begin(LORA_FREQ_HZ)) return false;
  applyRadioSettings();
  return true;
}

// --- RPC: transmit one frame, report airtime (runs in the main-loop thread) --
// Registered with provide_safe so it is serialised with loop()'s radio access —
// the SX1278 is on SPI and must never be touched from two threads at once.
static int lora_tx(MsgPack::bin_t<uint8_t> payload) {
  if (!radio_ok) return TX_ERR_RADIO_DOWN;
  const int len = (int)payload.size();
  if (len <= 0 || len > MAX_PAYLOAD) return TX_ERR_BAD_LEN;

  const unsigned long t0 = millis();
  if (LoRa.beginPacket() == 0) {
    // A healthy radio can NEVER be mid-transmit here: endPacket() below blocks until
    // the frame is fully on air, and RPC handlers are serialised with loop(). So a
    // busy answer means the SX1278 has WEDGED in TX mode (glitched register / lost
    // TxDone). Left alone it stays wedged forever and every frame — including an SOS —
    // is refused. Self-heal instead: standby first, full re-init as the last resort.
    LoRa.idle();                            // force STANDBY, clearing a stuck TX mode
    if (LoRa.beginPacket() == 0) {
      radio_ok = radioBegin();              // radio still stuck — re-init it outright
      if (!radio_ok) return TX_ERR_RADIO_DOWN;
      if (LoRa.beginPacket() == 0) {        // give up on this frame; radio is healthy now
        LoRa.receive();
        return TX_ERR_RADIO_BUSY;
      }
    }
  }
  LoRa.write(payload.data(), len);
  LoRa.endPacket();                         // blocks until the frame is fully on air
  const int airtime = (int)(millis() - t0);
  LoRa.receive();                           // back to listening
  return airtime;
}

// --- RPC: liveness + active settings banner ---------------------------------
static String lora_ping() {
  String s;
  s += String(LORA_FREQ_HZ); s += ' ';
  s += String(LORA_SF);      s += ' ';
  s += String(LORA_BW_HZ);   s += ' ';
  s += String(LORA_CR4);     s += ' ';
  s += String(LORA_SYNC, HEX);
  s += radio_ok ? " ok" : " down";
  return s;
}

void setup() {
  // Bridge first: begin() blocks until the router link is up, then registers routes.
  Bridge.begin();
  Monitor.begin(115200);            // human logs → `arduino-app-cli monitor`

  radio_ok = radioBegin();

  // provide_safe → handlers run in the main-loop thread (see loop()), so SPI is never
  // touched concurrently with pollRadio().
  Bridge.provide_safe("lora_tx", lora_tx);
  Bridge.provide_safe("lora_ping", lora_ping);

  if (radio_ok) {
    LoRa.receive();                 // continuous receive; parsePacket() polls it below
    Monitor.println("# LoRa modem ready");
  } else {
    Monitor.println("# LoRa init FAILED: check SS/RST/DIO0 wiring and 3V3 power");
  }
  Monitor.print("# "); Monitor.println(lora_ping());
}

void loop() {
  // Forward anything that arrived over the air. Runs in the main-loop thread; the
  // Bridge's __loopHook drains provide_safe() calls (lora_tx) right after this returns,
  // so radio access from RX and TX never overlaps.
  if (radio_ok) {
    const int packetSize = LoRa.parsePacket();
    if (packetSize > 0) {
      MsgPack::bin_t<uint8_t> payload;
      payload.reserve(packetSize);
      while (LoRa.available() && (int)payload.size() < MAX_PAYLOAD) {
        payload.push_back((uint8_t)LoRa.read());
      }
      const int   rssi = LoRa.packetRssi();
      const float snr  = LoRa.packetSnr();
      Bridge.notify("lora_rx", payload, rssi, snr);
    }
  }
}
