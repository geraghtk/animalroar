# AnimalRaw

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Animal 'Raw' detection escape room prop

Target board: **nicla_voice** (PlatformIO platform `nordicnrf52`, framework `arduino`).

## Build & Flash Commands

This is a PlatformIO project. There is no npm/make — use the `pio` CLI or the PlatformIO IDE extension for VS Code.

```bash
# Build
platformio run -e nicla_voice

# Build and flash
platformio run -e nicla_voice --target upload

# Open serial monitor (115200 baud)
platformio run -e nicla_voice --target monitor

# Build, flash, and monitor in one step
platformio run -e nicla_voice --target upload --target monitor

# Clean
platformio run --target clean
```

## Architecture

<!-- TODO: describe the firmware architecture as the project develops. Include:
     - Top-level loop responsibilities
     - Hardware peripherals and their pins
     - Any deferred-work / task split (e.g. ISR -> main loop flag flips)
     - Persistent storage (NVRAM / flash) usage
-->

## Arduino / PlatformIO Workflow

**`pio` location on this machine:**
```
C:/Users/Kevin/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0/LocalCache/local-packages/Python313/Scripts/pio.exe
```

**Serial port:** COM4. Always kill any running `pio.exe` monitor before flashing (`taskkill /F /IM pio.exe`) — the serial port can only be open in one process at a time. If the board enumerates as native USB CDC, a data-capable USB cable is required (not power-only).

**Diagnostic / test sketches:** Never overwrite the main `.ino` for temporary testing. Save diagnostic code to a separate file with a `.txt` extension (e.g. `src/MyTool.ino.txt`) — PlatformIO ignores `.txt` files, so they live alongside the real source without ever being compiled into the firmware.

## Dependencies

See `platformio.ini` for the canonical list of libraries and pinned versions. Add new dependencies under `lib_deps` rather than vendoring them into `lib/`.
