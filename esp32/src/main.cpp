// AnimalRaw — ESP32 intensity gate. See docs/wiring.md for the full topology.

#include <Arduino.h>
#include <math.h>
#include <Adafruit_NeoPixel.h>

// ── Pins ──────────────────────────────────────────────────────────────────────
#define MIC_ADC_PIN   34   // MAX9814 OUT → ADC1_CH6 (input-only, ADC1 = WiFi-safe)
#define MONKEY_IN_PIN  4   // input from Nicla DETECT_OUT_PIN
#define RELAY_PIN     13   // output to maglock relay
#define RELAY_ACTIVE  HIGH // level that releases the lock
#define STATUS_PIN    26   // 7-pixel WS2812B (red idle / green detected)
#define METER_PIN     27   // 16-pixel ring (intensity meter)

#define STATUS_NUM_PIXELS  7
#define METER_NUM_PIXELS  16
#define LED_BRIGHTNESS    64   // 0–255; keeps peak current sane

// ── Tuning ────────────────────────────────────────────────────────────────────
#define ADC_SAMPLES_PER_WINDOW 1024  // ~13 ms at ~75 kHz analogRead rate
#define INTENSITY_THRESHOLD     200  // RMS in ADC counts — tune empirically (see logs)
#define INTENSITY_WINDOW_MS    2000  // "recently loud" lookback
#define UNLOCK_DURATION_MS     5000  // ms maglock stays released

// ── State ─────────────────────────────────────────────────────────────────────
static uint16_t adcBuf[ADC_SAMPLES_PER_WINDOW];
static float currentRms = 0;
static unsigned long lastLoudMs = 0;
static unsigned long unlockTime = 0;
static bool unlocked = false;

static Adafruit_NeoPixel statusRing(STATUS_NUM_PIXELS, STATUS_PIN, NEO_GRB + NEO_KHZ800);
static Adafruit_NeoPixel meterRing(METER_NUM_PIXELS,   METER_PIN,  NEO_GRB + NEO_KHZ800);

// ── ADC setup ─────────────────────────────────────────────────────────────────
static void setupAdc() {
  analogReadResolution(12);                  // 0–4095
  analogSetPinAttenuation(MIC_ADC_PIN, ADC_11db);  // full 0–~3.3 V range
}

// MAX9814 outputs an analog audio signal centred on a ~1.25 V DC bias. We sample
// fast in a tight loop, subtract the per-window mean (handles bias drift +
// AGC-induced level shifts), then RMS the residual. Result is in ADC counts.
static void readMicAndComputeRms() {
  uint32_t sum = 0;
  for (int i = 0; i < ADC_SAMPLES_PER_WINDOW; i++) {
    adcBuf[i] = analogRead(MIC_ADC_PIN);
    sum += adcBuf[i];
  }
  int32_t mean = sum / ADC_SAMPLES_PER_WINDOW;
  uint64_t sumSq = 0;
  for (int i = 0; i < ADC_SAMPLES_PER_WINDOW; i++) {
    int32_t s = (int32_t)adcBuf[i] - mean;
    sumSq += (uint64_t)((int64_t)s * s);
  }
  currentRms = sqrtf((float)sumSq / ADC_SAMPLES_PER_WINDOW);
}

static void doUnlock() {
  digitalWrite(RELAY_PIN, RELAY_ACTIVE);
  unlocked = true;
  unlockTime = millis();
  Serial.print("UNLOCK rms="); Serial.println(currentRms, 0);
}

static void doRelock() {
  digitalWrite(RELAY_PIN, !RELAY_ACTIVE);
  unlocked = false;
  Serial.println("RELOCK");
}

// 7-pixel status ring: solid red while idle, solid green while monkey is detected.
static void updateStatusRing(bool monkeyDetected) {
  uint32_t color = monkeyDetected ? statusRing.Color(0, 255, 0)
                                  : statusRing.Color(255, 0, 0);
  for (uint16_t i = 0; i < STATUS_NUM_PIXELS; i++) {
    statusRing.setPixelColor(i, color);
  }
  statusRing.show();
}

// 16-pixel intensity meter: number of lit pixels = currentRms / INTENSITY_THRESHOLD,
// coloured green→yellow→red along the ring so the visual gets "hotter" as it fills.
static void updateMeterRing(float rms) {
  int lit = (int)((rms / (float)INTENSITY_THRESHOLD) * METER_NUM_PIXELS);
  if (lit < 0) lit = 0;
  if (lit > METER_NUM_PIXELS) lit = METER_NUM_PIXELS;

  for (int i = 0; i < METER_NUM_PIXELS; i++) {
    if (i < lit) {
      // Hue from 96 (green) at i=0 down to 0 (red) at i=METER_NUM_PIXELS-1
      uint16_t hue = (uint16_t)((96UL * (METER_NUM_PIXELS - 1 - i)) / (METER_NUM_PIXELS - 1));
      meterRing.setPixelColor(i, meterRing.ColorHSV(hue * 256, 255, 255));
    } else {
      meterRing.setPixelColor(i, 0);
    }
  }
  meterRing.show();
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(MONKEY_IN_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  doRelock();          // safe default

  statusRing.begin();
  statusRing.setBrightness(LED_BRIGHTNESS);
  meterRing.begin();
  meterRing.setBrightness(LED_BRIGHTNESS);
  updateStatusRing(false);
  updateMeterRing(0);

  setupAdc();
  Serial.println("ESP32 intensity gate ready");
}

void loop() {
  readMicAndComputeRms();
  if (currentRms > INTENSITY_THRESHOLD) {
    lastLoudMs = millis();
  }

  bool monkeyDetected = digitalRead(MONKEY_IN_PIN) == HIGH;
  bool recentlyLoud   = (millis() - lastLoudMs) < INTENSITY_WINDOW_MS;

  if (!unlocked && monkeyDetected && recentlyLoud) {
    doUnlock();
  }
  if (unlocked && (millis() - unlockTime >= UNLOCK_DURATION_MS)) {
    doRelock();
  }

  updateStatusRing(monkeyDetected);
  updateMeterRing(currentRms);

  // Status print every ~500 ms — useful for tuning INTENSITY_THRESHOLD
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus > 500) {
    lastStatus = millis();
    Serial.print("rms="); Serial.print(currentRms, 0);
    Serial.print(" monkey="); Serial.print(monkeyDetected);
    Serial.print(" loud=");   Serial.println(recentlyLoud);
  }
}
