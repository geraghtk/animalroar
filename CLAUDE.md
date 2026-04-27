# AnimalRaw

Escape-room prop. Children make monkey sounds → on-device classifier (Nicla Voice / Syntiant NDP120) detects `monkey` → companion ESP32 verifies sound is loud enough → relay releases a maglock on a crate.

Status: **working end-to-end** as of 2026-04-27 (Nicla side fully functional; ESP32 side coded, awaiting wiring).

## Architecture (two boards)

```
audio → Nicla Voice (NDP120 classifier)
         │ GPIO 5 = "monkey detected" (HIGH for 5s on unlock)
         ▼
         ESP32 + INMP441 I2S mic
         │ ANDs Nicla signal with RMS > INTENSITY_THRESHOLD
         ▼
         Relay → maglock
```

Common ground between the two boards is required.

The Nicla's mic is locked behind the NDP120 in keyword-spotting deployment mode — you can't read raw audio from it. That's why intensity is offloaded to the ESP32 with its own mic.

## Build & flash

```bash
# Nicla (PlatformIO project root)
pio run -e nicla_voice                    # build
pio run -e nicla_voice --target upload    # flash
pio run -e nicla_voice --target monitor   # serial @ 115200

# ESP32 (subdirectory)
cd esp32
pio run --target upload
pio run --target monitor
```

`pio` lives at:
```
C:/Users/Kevin/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0/LocalCache/local-packages/Python313/Scripts/pio.exe
```

Serial port: **COM5** (Nicla). Kill any open monitor before flashing — serial can only be open in one process. If the Nicla doesn't enumerate, the USB cable must be data-capable (not power-only).

## Edge Impulse — project 975711

Cloned from "Syntiant-RC-Go-Stop-NDP120" (412552). The clone is what gives us the `syntiant-nicla-ndp120` deployment target — generic EI projects can't export `.synpkg`.

- API key: keep in a local environment variable named `EI_API_KEY`; do not commit it.
- Classes: `monkey` + `z_openset` (negative catch-all, must be alphabetically last for Syntiant)
- Posterior params: `monkey` phth=0.7, phwin=5, phbackoff=20

## Re-running the pipeline

`src/ei_pipeline.py` orchestrates clear / upload / relabel / train / download. The **one critical step the pipeline does NOT do** is setting Syntiant posterior parameters — these don't auto-derive from training data, and a cloned Syntiant project keeps the tutorial's `go`/`stop` values forever unless you set them explicitly. Forgetting this produces a synpkg whose posterior handler points to NN output indices that don't exist in the trained model — the NDP fires zero match interrupts and the prop is silent. (We burned a long debugging session on this.)

```bash
# 1. Add/replace audio in momkeysounds/, then chop to 1s WAVs
python src/ei_pipeline.py prep

# 2. Wipe + upload + add EI noise library + relabel
python src/ei_pipeline.py clear
python src/ei_pipeline.py upload

# 3. SET POSTERIOR PARAMS (the easy-to-forget step):
python -c "
import os
import edgeimpulse_api
from edgeimpulse.experimental import api as exp_api
client = exp_api.EdgeImpulseApi(key=os.environ['EI_API_KEY'])
params = {'ph_type':'SC','states':[{'timeout':0,'timeout_action':'stay','timeout_action_arg':0,
  'classes':[{'label':'monkey','phwin':5,'phth':0.7,'phbackoff':20,
              'phaction':0,'phaction_arg':0,'smoothing_queue_size':1}]}]}
print(client.deployment.set_syntiant_posterior(project_id=975711,
    set_syntiant_posterior_request=edgeimpulse_api.SetSyntiantPosteriorRequest(parameters=params)))
"

# 4. Train + build + download synpkgs into deployment/syntiant-nicla-ndp120/ndp120/
python src/ei_pipeline.py train
python src/ei_pipeline.py download
```

The `download` command extracts the deployment ZIP and refreshes `deployment/syntiant-nicla-ndp120/ndp120/{mcu_fw_120_v91,dsp_firmware_v91,ei_model}.synpkg`.

## Re-flashing the Nicla after a new build

The Nicla SPI flash holds the synpkgs separately from the MCU firmware. The EI uploader needs the EI AT-command firmware running on the board (the prop firmware doesn't expose AT). Three steps:

```bash
# 1. Flash EI AT firmware so the uploader can talk to the board
"C:/Users/Kevin/.platformio/packages/tool-openocd/bin/openocd.exe" \
  -s "C:/Users/Kevin/.platformio/packages/tool-openocd/openocd/scripts" \
  -f interface/cmsis-dap.cfg -f target/nrf52.cfg \
  -c "program {C:/Users/Kevin/AnimalRaw/deployment/syntiant-nicla-ndp120/firmware.ino.elf} verify reset exit"

# 2. Format SPI flash + upload synpkgs (-f formats, -p programs)
cd deployment/syntiant-nicla-ndp120/ndp120
python ei_uploader.py -s COM5 -f -p \
  -a "C:/Users/Kevin/AnimalRaw/deployment/syntiant-nicla-ndp120/ndp120/syntiant-uploader-win.exe"

# 3. Reflash the prop firmware
cd ../../..
pio run -e nicla_voice --target upload
```

`ei_uploader.py` only knows three filenames (mcu_fw, dsp_firmware, ei_model). To upload an arbitrary synpkg (e.g. the bundled Alexa baseline for hardware diagnosis), use `deployment/syntiant-nicla-ndp120/ndp120/upload_any.py <files...>`.

## Tuning knobs

| Where | Knob | Current | Notes |
|---|---|---|---|
| EI Studio (rebuild) | `phth` | 0.7 | Per-frame NN confidence floor |
| EI Studio (rebuild) | `phwin` | 5 | Frames of sustained confidence |
| Nicla `main.ino` | `DEBOUNCE_FRAMES` | 3 | NDP matches before unlock |
| Nicla `main.ino` | `UNLOCK_DURATION_MS` | 5000 | DETECT_OUT_PIN HIGH duration |
| ESP32 `main.cpp` | `INTENSITY_THRESHOLD` | 3000 | RMS gate (raise if speech triggers) |
| ESP32 `main.cpp` | `INTENSITY_WINDOW_MS` | 2000 | "Recently loud" lookback |

The first three (Nicla side) interact: a louder/clearer monkey sound clears more frames at higher confidence and fires more matches in succession. There's no separate "intensity" reading on the Nicla — that's why the ESP32 exists.

## Hardware diagnosis

If the prop ever falls completely silent (no matches, no events):

1. Run the bundled Alexa baseline: copy `framework-arduino-mbed/libraries/NDP/extra/alexa_334_NDP120_B0_v11_v91.synpkg` to the deployment dir, upload with `upload_any.py`, flash a sketch that loads it (the AlexaDemo example or our minimal version). Saying "Alexa" should fire `MATCH: NN0:alexa`. If it does, the hardware is fine and the issue is in the EI build (almost always posterior params or training data).
2. If even Alexa doesn't fire — suspect synpkg upload corruption (re-run `ei_uploader.py -f -p`) or a hardware fault.

## Diagnostic sketches

PlatformIO ignores `.txt` extensions, so save throwaway sketches as `src/whatever.ino.txt` to keep them in the repo without compiling them into the firmware. Don't overwrite `main.ino` for temporary testing.

## Dependencies

Nicla — see `platformio.ini`. The custom `boards/nicla_voice.json` and the patch to `~/.platformio/platforms/nordicnrf52/platform.py` (routing nicla_voice to framework-arduino-mbed) are required because PIO doesn't ship Nicla Voice support.

ESP32 — see `esp32/platformio.ini`. Stock `espressif32` platform, no custom hardware setup.

Python pipeline — `pip install edgeimpulse soundfile requests`. `ffmpeg` on PATH (WinGet: `winget install Gyan.FFmpeg`). **Never use pydub** — its `audioop` dependency was removed in Python 3.13.
