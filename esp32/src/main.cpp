// AnimalRaw — ESP32 intensity gate
//
// Wiring:
//   INMP441 MEMS mic              ESP32
//     VDD  ────────────────────── 3V3
//     GND  ────────────────────── GND
//     L/R  ────────────────────── GND   (selects left channel)
//     WS   ────────────────────── GPIO 25
//     SCK  ────────────────────── GPIO 32
//     SD   ────────────────────── GPIO 33
//
//   Nicla Voice                   ESP32
//     GPIO 5 (DETECT_OUT_PIN) ─── GPIO 4    (input, "monkey detected")
//     GND  ────────────────────── GND       (common ground REQUIRED)
//
//   Maglock relay module          ESP32
//     IN   ────────────────────── GPIO 13
//     VCC  ────────────────────── 5V (or 3V3 if relay supports it)
//     GND  ────────────────────── GND
//   Maglock circuit goes through the relay's COM/NO contacts.
//   If your relay is active-LOW, flip RELAY_ACTIVE below.

#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

// ── Pins ──────────────────────────────────────────────────────────────────────
#define I2S_WS        25
#define I2S_SCK       32
#define I2S_SD        33
#define MONKEY_IN_PIN  4   // input from Nicla DETECT_OUT_PIN
#define RELAY_PIN     13   // output to maglock relay
#define RELAY_ACTIVE  HIGH // level that releases the lock

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

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(MONKEY_IN_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  doRelock();          // safe default

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

  // Status print every ~500 ms — useful for tuning INTENSITY_THRESHOLD
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus > 500) {
    lastStatus = millis();
    Serial.print("rms="); Serial.print(currentRms, 0);
    Serial.print(" monkey="); Serial.print(monkeyDetected);
    Serial.print(" loud=");   Serial.println(recentlyLoud);
  }
}
