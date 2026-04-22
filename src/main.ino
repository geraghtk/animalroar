#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  // Brief wait for native USB CDC enumeration; harmless on UART-only boards.
  while (!Serial && millis() < 3000) {}
  Serial.println("AnimalRaw booting...");
}

void loop() {
}
