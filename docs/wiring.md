# Wiring

The breadboard is a wiring hub, not a mounting surface. The only thing physically on it is a USB power module driving 5 V / 3.3 V / GND rails; everything else (Nicla Voice, ESP32, INMP441 mic, relay module, two NeoPixel rings) lives off-board and connects to the rails — and to each other — via flying wires. The maglock has its own supply; only its switching contacts touch the relay.

Two indicator NeoPixels, both driven by the ESP32:
- **7-pixel WS2812B** — listening state. Red while idle, green when the Nicla reports a detection.
- **16-pixel ring** — intensity meter. Pixels light up as the ESP32's RMS rises; full ring = unlock fires.

```
On breadboard
─────────────
  USB power module ──▶ 5V rail
                   ──▶ 3V3 rail
                   ──▶ GND rail

Off-board modules (each connects to the rails by flying wires)
──────────────────────────────────────────────────────────────
  Nicla Voice
  ESP32
  INMP441 mic
  Relay module
  7-pixel WS2812B    (status: red → green)
  16-pixel ring      (intensity meter)

Power
─────
  5V rail   ──▶ Nicla VIN (J2-9)
            ──▶ ESP32 VIN
            ──▶ Relay VCC
            ──▶ 7-pixel ring  VCC
            ──▶ 16-pixel ring VCC

  3V3 rail  ──▶ INMP441 VDD

  GND rail  ──▶ Nicla GND (J2-6)
            ──▶ ESP32 GND
            ──▶ Relay GND
            ──▶ INMP441 GND + L/R          (L/R tied to GND = left channel)
            ──▶ 7-pixel ring  GND
            ──▶ 16-pixel ring GND

  Relay COM/NO ──▶ maglock (separate PSU, isolated from breadboard)

Signals (3.3 V logic, direct module-to-module jumpers)
──────────────────────────────────────────────────────
  Nicla J1-1 (D5)  ──▶ ESP32 GPIO 4        "monkey detected"
  ESP32 GPIO 25    ──▶ INMP441 WS
  ESP32 GPIO 32    ──▶ INMP441 SCK
  ESP32 GPIO 33    ◀── INMP441 SD          (audio data into ESP32)
  ESP32 GPIO 13    ──▶ Relay IN
  ESP32 GPIO 26    ──▶ 7-pixel ring  DIN   (status indicator)
  ESP32 GPIO 27    ──▶ 16-pixel ring DIN   (intensity meter)
```

The two pin numbers above the link are the only place this needs to stay in sync with code:
- Nicla pin → `DETECT_OUT_PIN` in `src/main.ino`
- ESP32 pin → `MONKEY_IN_PIN` in `esp32/src/main.cpp`

## Power rails

| From | To | Voltage |
|---|---|---|
| USB power module 5 V out  | Breadboard 5 V rail  | 5 V |
| USB power module 3V3 out  | Breadboard 3V3 rail  | 3.3 V |
| USB power module GND out  | Breadboard GND rail  | — |
| 5 V rail | Nicla **VIN (J2-9)** | 5 V — *not* 3V3, the on-board PMIC needs 5 V |
| 5 V rail | ESP32 **VIN** (or 5V pin, depending on dev board) | 5 V |
| 5 V rail | Relay module **VCC** | 5 V |
| 5 V rail | 7-pixel WS2812B **VCC**, 16-pixel ring **VCC** | 5 V |
| 3V3 rail | INMP441 **VDD** | 3.3 V |
| GND rail | Nicla **J2-6**, ESP32 **GND**, INMP441 **GND** + **L/R**, Relay **GND**, both rings **GND** | — |

One common GND across everything — that's what gives the digital signals a meaningful reference.

### About the relay and maglock

The relay coil draws ~70–150 mA (5 V relays). A typical USB power module will handle that, but the **maglock itself must have its own supply** — it's well above what USB can do. The relay's COM/NO contacts are isolated from its IN signal, so the maglock circuit never touches the breadboard rails.

## Inter-board signal: Nicla → ESP32

| Nicla pad | PDF label | ESP32 pin | Purpose |
|---|---|---|---|
| **J1-1** | D5 / LPIO0_EXT / P0_24 | **GPIO 4** | "Monkey detected" signal, HIGH for 5 s on unlock |

(GND is already shared via the rail — no separate GND wire needed between the boards.)

### Finding the pads on the Nicla

There are **no silkscreen labels** on the Nicla Voice pin pads. You count, using `boards/ABX00061-full-pinout.pdf` (page 1, TOP VIEW) as the map.

- **J1** = the row of **8 pads** (no power pins — all signals: D5–D9, A0, A1, plus one NC).
- **J2** = the row of **9 pads** (has VIN, VDDIO_EXT, GND, NC, and D0–D4).
- Pin 1 of each row is the corner pad **nearest the J3 battery JST** (the 4-pin JST on the edge opposite the USB).

So **D5 = J1-1** is the corner pad on the 8-pad row, on the battery-JST end. **VIN = J2-9** and **GND = J2-6** are on the 9-pad row, counted from the same end.

### Mounting the Nicla

The Nicla isn't on the breadboard — it sits off-board on its own. The Nicla Voice has **castellated pads, not through-holes**, so wires get soldered directly: tin the inside of each half-circle and reflow a wire onto it. Three pads to wire:

- **J1-1** (D5) → ESP32 GPIO 4
- **J2-6** (GND) → GND rail
- **J2-9** (VIN) → 5 V rail

A dab of hot glue or kapton across the wires after soldering keeps them from peeling pads off if the cable gets tugged.

### Electrical notes

- Both boards run 3.3 V logic — D5 → GPIO 4 is a direct connection, no level shifter.
- All Nicla LPIO pads (including D5) are routed through a low-power bidirectional level shifter powered by `VDDIO_EXT` (defaults to 3.3 V via the PMIC LDO). Per the pinout PDF: these translators "can only drive very limited current." Driving a high-impedance ESP32 input is fine; do not source real load off D5.
- Keep the signal wire short, or twist it with a GND return — the NDP120 is sensitive to its own analog supply, and long unshielded GPIO runs near the mic can couple noise.

### Verification before plugging into the ESP32

Multimeter between J1-1 and any GND on the Nicla:
- Idle: 0 V
- Make a monkey sound: ~3.3 V for 5 s, then back to 0 V

If that works, the rest is just `digitalRead` on the ESP32 side.

## ESP32 local wiring

Lifted from `esp32/src/main.cpp:3-21`:

### INMP441 MEMS mic (I2S input for intensity gate)

| INMP441 | Connected to |
|---|---|
| VDD | 3V3 rail |
| GND | GND rail |
| L/R | GND rail (selects left channel) |
| WS  | ESP32 GPIO 25 |
| SCK | ESP32 GPIO 32 |
| SD  | ESP32 GPIO 33 |

### Maglock relay

| Relay module | Connected to |
|---|---|
| IN  | ESP32 GPIO 13 |
| VCC | 5 V rail |
| GND | GND rail |
| COM / NO | Maglock circuit (separate PSU) |

If the relay is active-LOW, flip `RELAY_ACTIVE` in `esp32/src/main.cpp`.

### NeoPixel indicators (WS2812B)

| Ring | Pin | Connected to |
|---|---|---|
| 7-pixel (status) | DIN | ESP32 GPIO 26 (via 330–470 Ω resistor) |
| 7-pixel (status) | VCC, GND | 5 V rail, GND rail |
| 16-pixel (intensity) | DIN | ESP32 GPIO 27 (via 330–470 Ω resistor) |
| 16-pixel (intensity) | VCC, GND | 5 V rail, GND rail |

Per Adafruit's NeoPixel guidance:
- **Series resistor on each DIN line** (~330–470 Ω, close to the ring) — prevents transient ringing on the data edge that can corrupt the first pixel.
- **Bulk capacitor across each ring's VCC/GND** (470 µF or larger, close to the ring) — smooths inrush when a lot of pixels turn on at once.

#### 3.3 V → 5 V data-line note

WS2812B data input is spec'd at `Vih ≥ 0.7 × Vdd` — 3.5 V min when the ring runs at 5 V. The ESP32 outputs 3.3 V, so it's technically below spec. In practice it usually works on short data runs because the first pixel re-buffers a clean 5 V level for the rest of the chain. If you see flicker, wrong colours, or the first pixel misbehaving:

1. **Drop the ring supply by ~0.7 V**: put a 1N4001 in series with the 5 V rail going into the ring's VCC. Brings the Vih threshold to ~3.0 V, which the ESP32 meets cleanly. Easiest fix.
2. **Add a 74AHCT125 level shifter** between the ESP32 GPIO and the ring's DIN. Bulletproof.

### Power budget

Worst-case current draw on the 5 V rail at full white:
- 7-pixel ring: ~420 mA
- 16-pixel ring: ~960 mA
- Relay coil: ~150 mA
- Nicla + ESP32: ~200 mA combined

Total peak: ~1.7 A. The USB power module's source needs to be 2 A or better. Real-world draw will be much lower since neither ring will ever be all-white-all-on under the planned animations, but the supply has to survive the worst case during a ring fade-in or the ESP32 will brown-out and reset.
