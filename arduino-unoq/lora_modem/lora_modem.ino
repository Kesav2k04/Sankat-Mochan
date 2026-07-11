/*
 * Sankat-Mochan — field-side LoRa modem for the Arduino UNO Q (STM32 / Arduino side)
 * =================================================================================
 *
 * WHAT THIS IS
 *   When both Ra-02 radios sat on the Raspberry Pi, the Pi ran two "MeshNode"s and
 *   drove both radios directly over SPI. Now the FIELD radio has moved to the UNO Q.
 *   This sketch turns that radio into a transparent LoRa modem: it does nothing but
 *   move bytes between 433 MHz and the serial link. The real field-node logic (BLE to
 *   the victim's phone, envelope validation, dedup, forwarding) still runs as the same
 *   Python code — on the UNO Q's Linux side now instead of the Pi — talking to this
 *   sketch over serial. So the app behaves exactly as it did on the two-radio Pi.
 *
 *       victim phone --BLE--> [UNO Q Linux: field node] --serial--> [THIS SKETCH]
 *                                                                        ~~433 MHz~~>  Pi gateway --> dashboard
 *
 * RADIO LIBRARY
 *   arduino-LoRa by Sandeep Mistry — MIT licensed (project rule 1). Install it once:
 *     Arduino IDE -> Tools -> Manage Libraries -> search "LoRa" by Sandeep Mistry.
 *   Source: https://github.com/sandeepmistry/arduino-LoRa  (public, MIT).
 *   This is the same <LoRa.h> your working bring-up sketch used.
 *
 * WIRING (the pins you already verified: SS=10, RST=9, DIO0=2)
 *     SX1278 (Ra-02)   ->  UNO Q Arduino header
 *       NSS / SS       ->  D10
 *       RST            ->  D9
 *       DIO0           ->  D2
 *       SCK            ->  D13 (hardware SPI)
 *       MOSI           ->  D11 (hardware SPI)
 *       MISO           ->  D12 (hardware SPI)
 *       3V3            ->  3V3   (NEVER 5 V — a Ra-02 is a 3.3 V part)
 *       GND            ->  GND
 *       ANT            ->  antenna, ALWAYS attached before power (never TX bare)
 *
 * !! THE SETTINGS BELOW MUST MATCH pi-code/config.example.json  (the "lora" block) !!
 *    433 MHz, SF7, BW 125 kHz, coding rate 4/5, sync word 0x12, preamble 8, CRC on.
 *    If any one of these differs, the Pi's gateway radio will not hear this one at all.
 *
 * SERIAL LINE PROTOCOL  (ASCII, one message per line, terminated with '\n')
 *   The UNO Q's Linux side is the HOST; this sketch is the MODEM. Payload bytes are
 *   sent as lowercase hex so a line can never contain a stray newline or control byte.
 *
 *     HOST  -> MODEM
 *       T <hex>            transmit these bytes over 433 MHz  (<= MAX_PAYLOAD bytes)
 *       P                  ping / health check
 *
 *     MODEM -> HOST
 *       R <hex> <rssi> <snr>   a frame arrived (CRC already checked by the radio)
 *       K <airtime_ms>         the preceding T finished transmitting
 *       E <reason>             the preceding T failed
 *       Y                      pong (reply to P)
 *       I <freq> <sf> <bw> <cr> <sync>   boot banner with the active settings
 *       # <text>               human-readable log line — the host parser ignores these
 */

#include <SPI.h>
#include <LoRa.h>

// --- pins (as verified on this board) ---------------------------------------
#define SS_PIN    10
#define RST_PIN    9
#define DIO0_PIN   2

// --- radio settings: keep in lock-step with pi-code/config.example.json ------
#define LORA_FREQ_HZ   433000000L   // frequency_hz
#define LORA_SF        7            // spreading_factor
#define LORA_BW_HZ     125000L      // bandwidth_hz
#define LORA_CR4       5            // coding_rate (4/5)
#define LORA_TX_POWER  5            // tx_power_dbm (PA_BOOST)
#define LORA_SYNC      0x12         // sync_word (18 decimal in the JSON)
#define LORA_PREAMBLE  8            // preamble_len
// CRC is enabled below (config crc:true). The library then drops CRC-failed frames
// on receive, so every frame we forward to the host is already known-good.

#define MAX_PAYLOAD    255          // matches lora.max_payload
#define LINE_MAX       600          // hex of 255 bytes = 510 chars, plus prefix/slack
#define SERIAL_BAUD    115200       // the baud your bring-up sketch used

static char    lineBuf[LINE_MAX];
static uint16_t lineLen = 0;
static uint8_t  frame[MAX_PAYLOAD];   // scratch for one decoded TX/RX payload

// --- tiny hex helpers (no library, works the same on both ends) --------------
static char hexDigit(uint8_t v) { return v < 10 ? char('0' + v) : char('a' + (v - 10)); }

static int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// Decode a hex string into `frame`. Returns the byte count, or -1 if malformed.
static int hexDecode(const char *s, uint16_t n) {
  if (n & 1) return -1;                 // hex must be an even number of chars
  uint16_t bytes = n / 2;
  if (bytes > MAX_PAYLOAD) return -1;
  for (uint16_t i = 0; i < bytes; i++) {
    int hi = hexVal(s[2 * i]);
    int lo = hexVal(s[2 * i + 1]);
    if (hi < 0 || lo < 0) return -1;
    frame[i] = uint8_t((hi << 4) | lo);
  }
  return bytes;
}

// Stream `len` bytes of `data` to the host as hex, without a big temp buffer.
static void hexPrint(const uint8_t *data, uint16_t len) {
  for (uint16_t i = 0; i < len; i++) {
    Serial.write(hexDigit(data[i] >> 4));
    Serial.write(hexDigit(data[i] & 0x0F));
  }
}

// --- radio bring-up ----------------------------------------------------------
static void applyRadioSettings() {
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW_HZ);
  LoRa.setCodingRate4(LORA_CR4);
  LoRa.setPreambleLength(LORA_PREAMBLE);
  LoRa.setSyncWord(LORA_SYNC);
  LoRa.setTxPower(LORA_TX_POWER);   // PA_BOOST pin, like the Pi driver
  LoRa.enableCrc();                 // config crc:true
}

static bool radioBegin() {
  LoRa.setPins(SS_PIN, RST_PIN, DIO0_PIN);
  if (!LoRa.begin(LORA_FREQ_HZ)) return false;
  applyRadioSettings();
  return true;
}

static void announce() {
  // The host reads this banner to confirm the modem is alive and on the right settings.
  // "I <freq> <sf> <bw> <cr> <sync-hex>"  e.g.  I 433000000 7 125000 5 12
  Serial.print("I ");
  Serial.print(LORA_FREQ_HZ);
  Serial.print(' '); Serial.print(LORA_SF);
  Serial.print(' '); Serial.print(LORA_BW_HZ);
  Serial.print(' '); Serial.print(LORA_CR4);
  Serial.print(' '); Serial.println(LORA_SYNC, HEX);
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  // Do NOT block on `while (!Serial)` here: on the UNO Q the Linux host may attach to
  // the serial link long after boot, and we must not hang the radio waiting for it.
  delay(50);

  if (!radioBegin()) {
    // Keep saying so — the host's pre-flight will see the modem never reports ready.
    while (true) {
      Serial.println("# LoRa init FAILED: check SS/RST/DIO0 wiring and 3V3 power");
      delay(2000);
    }
  }

  LoRa.receive();      // continuous receive; parsePacket() polls it in loop()
  Serial.println("# LoRa modem ready");
  announce();
}

// --- transmit one frame, report airtime -------------------------------------
static void doTransmit(int len) {
  unsigned long t0 = millis();
  if (LoRa.beginPacket() == 0) {          // radio busy / could not enter TX
    Serial.println("E radio_busy");
    LoRa.receive();
    return;
  }
  LoRa.write(frame, len);
  LoRa.endPacket();                       // blocks until the frame is fully on air
  unsigned long airtime = millis() - t0;

  Serial.print("K ");
  Serial.println(airtime);
  LoRa.receive();                         // back to listening
}

// --- handle one complete line from the host ---------------------------------
static void handleLine(char *s, uint16_t n) {
  if (n == 0) return;
  char cmd = s[0];

  if (cmd == 'P') {                       // ping
    Serial.println("Y");
    return;
  }
  if (cmd == 'T') {                       // transmit: "T <hex>"
    if (n < 2 || s[1] != ' ') { Serial.println("E bad_tx"); return; }
    int len = hexDecode(s + 2, n - 2);
    if (len <= 0) { Serial.println("E bad_hex"); return; }
    doTransmit(len);
    return;
  }
  // Unknown command — say so but keep running.
  Serial.println("# ignored unknown command");
}

// --- drain any received LoRa frame to the host ------------------------------
static void pollRadio() {
  int packetSize = LoRa.parsePacket();
  if (packetSize <= 0) return;            // nothing, or a CRC-failed frame the lib dropped

  uint16_t len = 0;
  while (LoRa.available() && len < MAX_PAYLOAD) {
    frame[len++] = (uint8_t)LoRa.read();
  }
  int   rssi = LoRa.packetRssi();
  float snr  = LoRa.packetSnr();

  Serial.print("R ");
  hexPrint(frame, len);
  Serial.print(' '); Serial.print(rssi);
  Serial.print(' '); Serial.println(snr, 2);
}

void loop() {
  // 1) Feed serial bytes into the line buffer; act on each complete '\n'-terminated line.
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[lineLen] = '\0';
      handleLine(lineBuf, lineLen);
      lineLen = 0;
    } else if (lineLen < LINE_MAX - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineLen = 0;                        // overlong line — drop it rather than overflow
      Serial.println("# line too long, dropped");
    }
  }

  // 2) Forward anything that arrived over the air.
  pollRadio();
}
