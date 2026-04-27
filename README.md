# AnimalRaw

Escape-room prop firmware for a crate that unlocks when players make a convincing, loud animal sound.

The current build is tuned for **monkey sounds**. A Nicla Voice runs the on-device classifier, while a companion ESP32 measures sound intensity with its own microphone. The maglock only releases when both boards agree: the sound matches the trained class and the sound is loud enough.

## Architecture

```text
audio -> Nicla Voice / Syntiant NDP120 classifier
          GPIO 5 HIGH when "monkey" is detected
          |
          v
          ESP32 + INMP441 I2S microphone
          checks recent RMS level against intensity threshold
          |
          v
          relay or driver -> maglock
```

The Nicla and ESP32 must share ground. The ESP32 is responsible for the final maglock control so the classifier signal and intensity gate can be combined in one place.

## Hardware

- Arduino Nicla Voice
- ESP32 development board
- INMP441 I2S microphone for intensity measurement
- Relay, MOSFET driver, or other maglock driver circuit
- Maglock and suitable power supply

Confirm maglock polarity and fail-safe behavior before connecting the lock to the prop.

## Firmware Layout

- `src/main.ino` - Nicla Voice firmware; loads the Syntiant `.synpkg` files and raises a GPIO signal when the target class is detected.
- `esp32/src/main.cpp` - ESP32 firmware; measures microphone RMS and releases the lock when the Nicla signal is active and intensity is high enough.
- `src/ei_pipeline.py` - Edge Impulse data, training, and deployment helper.
- `deployment/syntiant-nicla-ndp120/` - Syntiant deployment artifacts and upload tools.
- `boards/nicla_voice.json` - custom PlatformIO board definition.

## Setup

This project uses PlatformIO.

Create a local `.env` file for the Edge Impulse project key:

```text
EI_API_KEY=your_edge_impulse_project_api_key
```

Do not commit `.env`; it is ignored by git. Use `.env.example` as the template.

Install Python dependencies used by the training pipeline:

```bash
pip install edgeimpulse soundfile requests
```

The pipeline also expects `ffmpeg` on `PATH`.

## Build And Flash

Nicla Voice:

```bash
pio run -e nicla_voice
pio run -e nicla_voice --target upload
pio run -e nicla_voice --target monitor
```

ESP32:

```bash
cd esp32
pio run
pio run --target upload
pio run --target monitor
```

On the development machine this project was built around the Nicla on `COM5` at `115200` baud.

## Tuning

Primary tuning values:

- Nicla classifier target: `TARGET_LABEL` in `src/main.ino`
- Nicla detection strictness: `INFERENCE_THRESHOLD` and `DEBOUNCE_FRAMES` in `src/main.ino`
- Unlock pulse duration: `UNLOCK_DURATION_MS` in `src/main.ino`
- ESP32 loudness gate: `INTENSITY_THRESHOLD` and `INTENSITY_WINDOW_MS` in `esp32/src/main.cpp`
- Edge Impulse posterior parameters: `phth`, `phwin`, and `phbackoff`

The Nicla does not provide a separate raw loudness reading in this deployment mode, so intensity is intentionally measured by the ESP32 microphone path.

## Training Pipeline

`src/ei_pipeline.py` can prepare local audio clips, upload data to Edge Impulse, train, and download a Syntiant Nicla Voice deployment.

Typical flow:

```bash
python src/ei_pipeline.py prep
python src/ei_pipeline.py clear
python src/ei_pipeline.py upload
python src/ei_pipeline.py train
python src/ei_pipeline.py download
```

After retraining, confirm the Syntiant posterior parameters are set for the current class labels before flashing the new `.synpkg` files.

## Notes

Generated PlatformIO build output, local audio sources, processed audio clips, local Claude settings, and `.env` are intentionally ignored.

For deeper project notes and recovery procedures, see `CLAUDE.md`.
