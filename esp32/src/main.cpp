// AnimalRaw — ESP32 intensity gate. See docs/wiring.md for the full topology.

#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>
#include <Adafruit_NeoPixel.h>

// ── Pins ──────────────────────────────────────────────────────────────────────
#define I2S_WS        25
#define I2S_SCK       32
#define I2S_SD        33
#define MONKEY_IN_PIN  4   // input from Nicla DETECT_OUT_PIN
#define RELAY_PIN     13   // output to maglock relay
#define RELAY_ACTIVE  HIGH // level that releases the lock
#define STATUS_PIN    26   // 7-pixel WS2812B (red idle / green detected)
#define METER_PIN     27   // 16-pixel ring (intensity meter)

#define STATUS_NUM_PIXELS  7
#define METER_NUM_PIXELS  16
#define LED_BRIGHTNESS    64   // 0–255; keeps peak current sane

// ── Tuning ────────────────────────────────────────────────────────────────────
#define SAMPLE_RATE         16000
#define I2S_FRAMES_PER_READ   512   // ~32 ms windows
#define INTENSITY_THRESHOLD  3000   // RMS gate — tune empirically (see logs)
#define INTENSITY_WINDOW_MS  2000   // "recently loud" lookback
#define UNLOCK_DURATION_MS   5000   // ms maglock stays released

// ── State ─────────────────────────────────────────────────────────────────────
static int32_t i2sBuf[I2S_FRAMES_PER_READ];
static float currentRms = 0;
static unsigned long lastLoudMs = 0;
static unsigned long unlockTime = 0;
static bool unlocked = false;

static Adafruit_NeoPixel statusRing(STATUS_NUM_PIXELS, STATUS_PIN, NEO_GRB + NEO_KHZ800);
static Adafruit_NeoPixel meterRing(METER_NUM_PIXELS,   METER_PIN,  NEO_GRB + NEO_KHZ800);

// ── I2S setup ─────────────────────────────────────────────────────────────────
static void setupI2S() {
  i2s_config_t cfg = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = I2S_FRAMES_PER_READ,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0,
  };
  i2s_pin_config_t pins = {
    .bck_io_num = I2S_SCK,
    .ws_io_num  = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_SD,
  };
  i2s_driver_install(I2S_NUM_0, &cfg, 0, nullptr);
  i2s_set_pin(I2S_NUM_0, &pins);
}

// INMP441 outputs 24-bit data left-aligned in a 32-bit slot, so shift right 14
// to land in a sane int range. Compute RMS over the read window.
static void readMicAndComputeRms() {
  size_t bytesRead = 0;
  i2s_read(I2S_NUM_0, i2sBuf, sizeof(i2sBuf), &bytesRead, portMAX_DELAY);
  int n = bytesRead / sizeof(int32_t);
  if (n <= 0) { currentRms = 0; return; }
  uint64_t sumSq = 0;
  for (int i = 0; i < n; i++) {
    int32_t s = i2sBuf[i] >> 14;
    sumSq += (uint64_t)((int64_t)s * s);
  }
  currentRms = sqrtf((float)sumSq / n);
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

  setupI2S();
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
