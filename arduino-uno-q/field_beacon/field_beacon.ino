/*
 * Sankat-Mochan — self-contained LoRa field node for the Arduino UNO Q
 * ====================================================================
 *
 * This sketch makes the UNO Q a COMPLETE field node on its own — no Python, no Linux
 * side, nothing to install. It builds a real SOS envelope (the exact JSON the Pi's
 * gateway validates and puts on the dashboard) and transmits it over 433 MHz. It also
 * listens, so when a responder ACCEPTs on the dashboard the reply comes back over LoRa
 * and lights the LED here.
 *
 *   [UNO Q: this sketch]  ~~433 MHz~~►  [Pi: gateway]  ──►  AI command post / dashboard
 *   [UNO Q: this sketch]  ◄~~433 MHz~~  [Pi: gateway]  ◄──  responder taps ACCEPT
 *
 * Use this when the UNO Q's Linux side cannot install Python packages. The trade-off:
 * a victim's PHONE cannot hand an SOS to this board over Bluetooth (the STM32 has no
 * Bluetooth radio, and that path needs a BLE library on the Linux side). Instead the
 * UNO Q ORIGINATES the SOS itself — the "sensor / auto-SOS field node" role. Everything
 * downstream (Pi triage, translate, map, responder ACCEPT, dashboard) is unchanged.
 *
 * WHAT FIRES AN SOS
 *   - once at boot (so a demo shows immediately)
 *   - whenever you send any character in the Serial Monitor
 *   - a button from BUTTON_PIN to GND (optional; uses the internal pull-up)
 *   - automatically every AUTO_SOS_SECONDS (0 = off) for a hands-free demo
 *
 * RADIO LIBRARY
 *   arduino-LoRa by Sandeep Mistry — MIT (project rule 1). Install once:
 *   Arduino IDE -> Manage Libraries -> "LoRa" by Sandeep Mistry.  Same <LoRa.h> you used.
 *
 * WIRING (the pins you verified)   SX1278 (Ra-02) -> UNO Q header
 *   NSS=D10  RST=D9  DIO0=D2   SCK=D13  MOSI=D11  MISO=D12   3V3=3V3  GND=GND
 *   ANT: always attached before power.   3.3 V only — never 5 V.
 *
 * !! The radio settings below MUST match the Pi (raspberrypi/config.example.json "lora"):
 *    433 MHz, SF7, BW 125 kHz, CR 4/5, sync 0x12, preamble 8, CRC on. They already do. !!
 */

#include <SPI.h>
#include <LoRa.h>
#include <string.h>   // strstr

// --- pins --------------------------------------------------------------------
#define SS_PIN     10
#define RST_PIN     9
#define DIO0_PIN    2
#define BUTTON_PIN  3          // optional button to GND; leave unconnected if unused

// --- radio settings: keep in lock-step with the Pi --------------------------
#define LORA_FREQ_HZ   433000000L
#define LORA_SF        7
#define LORA_BW_HZ     125000L
#define LORA_CR4       5
#define LORA_TX_POWER  5
#define LORA_SYNC      0x12
#define LORA_PREAMBLE  8

// --- what this SOS says (edit freely for your demo) --------------------------
// Keep these plain ASCII with NO double-quotes or backslashes — they go straight into
// JSON. Coordinates are strings so we never depend on float printf support.
#define SOS_ORIGIN    "UNOQ"                               // <= 4 chars, alnum
#define SOS_URGENCY   5                                    // 1..5 (5 = life-threatening)
#define SOS_CATEGORY  "sensor"
#define SOS_LOCATION  "Sector 7 relief road"
#define SOS_GIST      "Auto-SOS: flood sensor tripped, water rising"
#define SOS_LAT       "12.97160"                           // decimal degrees, as text
#define SOS_LNG       "77.59460"

#define AUTO_SOS_SECONDS  0    // 0 = off; set e.g. 20 to fire hands-free every 20 s

#define MAX_ENVELOPE   244     // the Pi drops anything larger (envelope.py MAX_BYTES)

static char     bootTag[5];    // 4 hex chars, random per power-up, so ids stay unique
static uint32_t seqCounter = 0;
static unsigned long lastAutoMs = 0;
static int      lastButton = HIGH;

// --- helpers -----------------------------------------------------------------
static void makeBootTag() {
  // A little entropy so envelope ids don't repeat across reboots (which the Pi's dedup
  // would otherwise drop as already-seen). Analog noise + micros is plenty for a demo.
  uint32_t r = ((uint32_t)analogRead(A0) << 20) ^ ((uint32_t)analogRead(A1) << 8) ^ micros();
  const char *hexd = "0123456789abcdef";
  for (int i = 0; i < 4; i++) bootTag[i] = hexd[(r >> (i * 4)) & 0xF];
  bootTag[4] = '\0';
}

static void applyRadioSettings() {
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW_HZ);
  LoRa.setCodingRate4(LORA_CR4);
  LoRa.setPreambleLength(LORA_PREAMBLE);
  LoRa.setSyncWord(LORA_SYNC);
  LoRa.setTxPower(LORA_TX_POWER);
  LoRa.enableCrc();
}

static void blink(int times, int ms) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_BUILTIN, HIGH); delay(ms);
    digitalWrite(LED_BUILTIN, LOW);  delay(ms);
  }
}

// Build one SOS envelope into `out`. Returns its length, or -1 if it would be too big.
static int buildEnvelope(char *out, size_t cap) {
  seqCounter++;
  int n = snprintf(
    out, cap,
    "{\"i\":\"%s-%s-%lu\",\"t\":\"SOS\",\"o\":\"%s\",\"u\":%d,"
    "\"c\":\"%s\",\"l\":\"%s\",\"g\":\"%s\",\"ln\":\"en\","
    "\"la\":%s,\"lo\":%s,\"h\":0}",
    SOS_ORIGIN, bootTag, (unsigned long)seqCounter, SOS_ORIGIN, SOS_URGENCY,
    SOS_CATEGORY, SOS_LOCATION, SOS_GIST, SOS_LAT, SOS_LNG);
  if (n < 0 || n > (int)MAX_ENVELOPE || n >= (int)cap) return -1;
  return n;
}

static void sendSOS(const char *why) {
  char env[MAX_ENVELOPE + 1];
  int len = buildEnvelope(env, sizeof(env));
  if (len < 0) {
    Serial.println("# SOS too large — shorten SOS_GIST / SOS_LOCATION");
    return;
  }
  if (LoRa.beginPacket() == 0) {
    Serial.println("# radio busy, SOS not sent");
    LoRa.receive();
    return;
  }
  LoRa.write((const uint8_t *)env, len);
  LoRa.endPacket();                 // blocks until fully transmitted
  LoRa.receive();                   // back to listening for the ACCEPT

  Serial.print("TX SOS ("); Serial.print(why); Serial.print(", ");
  Serial.print(len); Serial.println(" bytes):");
  Serial.print("   "); Serial.println(env);
  blink(2, 60);
}

// Print (and light up on) anything that arrives back over the air — notably the
// responder's ACCEPTED coming home from the dashboard through the Pi gateway.
static void pollDownlink() {
  int sz = LoRa.parsePacket();
  if (sz <= 0) return;              // nothing, or a CRC-failed frame the library dropped

  char buf[MAX_ENVELOPE + 1];
  int i = 0;
  while (LoRa.available() && i < (int)MAX_ENVELOPE) buf[i++] = (char)LoRa.read();
  buf[i] = '\0';

  Serial.print("RX ("); Serial.print(LoRa.packetRssi()); Serial.print(" dBm, SNR ");
  Serial.print(LoRa.packetSnr(), 1); Serial.println("):");
  Serial.print("   "); Serial.println(buf);

  if (strstr(buf, "\"ACCEPTED\"") || strstr(buf, "ACCEPTED")) {
    Serial.println("   >>> a responder ACCEPTED — help is on the way <<<");
    blink(6, 40);
  } else {
    blink(1, 200);
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  delay(50);                        // do NOT wait on Serial — must run headless too

  makeBootTag();

  LoRa.setPins(SS_PIN, RST_PIN, DIO0_PIN);
  if (!LoRa.begin(LORA_FREQ_HZ)) {
    while (true) {
      Serial.println("# LoRa init FAILED: check SS/RST/DIO0 wiring and 3V3 power");
      blink(3, 120);
      delay(1500);
    }
  }
  applyRadioSettings();
  LoRa.receive();

  Serial.println("# Sankat-Mochan field beacon ready");
  Serial.print("# boot tag "); Serial.print(bootTag);
  Serial.println(" — press the button, send any char here, or wait for auto-SOS");

  sendSOS("boot");                  // fire one immediately so a demo shows right away
  lastAutoMs = millis();
}

void loop() {
  // 1) any Serial byte -> send an SOS (drain the rest of the line)
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    sendSOS("serial");
  }

  // 2) button press (active-low, simple debounce)
  int b = digitalRead(BUTTON_PIN);
  if (b == LOW && lastButton == HIGH) {
    delay(25);
    if (digitalRead(BUTTON_PIN) == LOW) sendSOS("button");
  }
  lastButton = b;

  // 3) optional hands-free timer
  if (AUTO_SOS_SECONDS > 0 && (millis() - lastAutoMs) >= (unsigned long)AUTO_SOS_SECONDS * 1000UL) {
    lastAutoMs = millis();
    sendSOS("auto");
  }

  // 4) anything coming back over the air (the responder's ACCEPT)
  pollDownlink();
}
