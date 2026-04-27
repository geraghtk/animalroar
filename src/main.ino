#include <Arduino.h>
#include "NDP.h"
#include <Nicla_System.h>

// ── Tuning ────────────────────────────────────────────────────────────────────
#define TARGET_LABEL        "NN0:monkey"
#define INFERENCE_THRESHOLD  180     // NDP hardware gate 0–255 (higher = stricter)
#define DEBOUNCE_FRAMES        3     // consecutive matches before unlock fires
#define UNLOCK_DURATION_MS  5000     // ms maglock stays released

// ── Hardware ──────────────────────────────────────────────────────────────────
// GPIO drives a "monkey detected" signal to the ESP32 intensity gate.
// ESP32 ANDs this with its own RMS check before releasing the maglock.
#define DETECT_OUT_PIN   5
#define DETECT_ACTIVE    HIGH

// ── State ─────────────────────────────────────────────────────────────────────
static volatile int  debounceCount = 0;
static volatile bool unlocked      = false;
static volatile unsigned long unlockTime = 0;

// ── Helpers ───────────────────────────────────────────────────────────────────
static void setLED(uint8_t r, uint8_t g, uint8_t b) {
  nicla::leds.setColor(r, g, b);
}

static void doUnlock() {
  digitalWrite(DETECT_OUT_PIN, DETECT_ACTIVE);
  unlocked   = true;
  unlockTime = millis();
  setLED(0, 0, 255);   // blue = unlocked
  Serial.println("UNLOCK");
}

static void doRelock() {
  digitalWrite(DETECT_OUT_PIN, !DETECT_ACTIVE);
  unlocked      = false;
  debounceCount = 0;
  setLED(0, 255, 0);   // green = listening
  Serial.println("RELOCK");
}

// ── NDP callbacks (ISR context — keep short) ──────────────────────────────────
void onMatch(char* label) {
  Serial.print("MATCH: ");
  Serial.println(label);

  if (strcmp(label, TARGET_LABEL) == 0) {
    debounceCount++;
    setLED(0, 0, 255);   // blue = accumulating
    Serial.print("count=");
    Serial.println(debounceCount);
    if (debounceCount >= DEBOUNCE_FRAMES && !unlocked) {
      doUnlock();
    }
  } else {
    debounceCount = 0;
    if (!unlocked) setLED(0, 255, 0);
  }
}

void onError() {
  setLED(255, 0, 0);   // red = error
  Serial.println("NDP ERROR");
}

static volatile uint32_t eventCount = 0;
void onEvent() {
  eventCount++;          // any non-match NDP interrupt
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(3000);

  nicla::begin();
  // nicla::disableLDO();   // disabled — was producing no inference
  nicla::leds.begin();
  setLED(255, 0, 0);   // red while loading

  pinMode(DETECT_OUT_PIN, OUTPUT);
  doRelock();          // safe default on boot

  Serial.println("AnimalRaw booting");
  Serial.print("Target: "); Serial.println(TARGET_LABEL);
  Serial.print("Threshold: "); Serial.println(INFERENCE_THRESHOLD);
  Serial.print("Debounce: "); Serial.println(DEBOUNCE_FRAMES);

  NDP.onMatch(onMatch);
  NDP.onError(onError);
  NDP.onEvent(onEvent);

  Serial.println("Loading mcu_fw...");
  NDP.begin("mcu_fw_120_v91.synpkg");

  Serial.println("Loading dsp_fw...");
  NDP.load("dsp_firmware_v91.synpkg");

  Serial.println("Loading model...");
  NDP.load("ei_model.synpkg");

  NDP.getInfo();
  int thStatus = NDP.configureInferenceThreshold(INFERENCE_THRESHOLD);
  Serial.print("configureInferenceThreshold ret = "); Serial.println(thStatus);
  int micStatus = NDP.turnOnMicrophone();
  Serial.print("turnOnMicrophone ret = "); Serial.println(micStatus);
  int chunk = NDP.getAudioChunkSize();
  Serial.print("audio chunk size = "); Serial.println(chunk);
  NDP.interrupts();

  setLED(0, 255, 0);   // green = listening
  Serial.println("Ready — make monkey sounds!");
}

// ── Loop ──────────────────────────────────────────────────────────────────────
static unsigned long lastHeartbeat = 0;

void loop() {
  if (unlocked && (millis() - unlockTime >= UNLOCK_DURATION_MS)) {
    doRelock();
  }

  if (millis() - lastHeartbeat >= 3000) {
    lastHeartbeat = millis();
    Serial.print("listening... events="); Serial.println(eventCount);
  }
  delay(100);
}
