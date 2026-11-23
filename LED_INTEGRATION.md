# LED + Music Integration Guide (WLED-inspired, DeskBuddy-safe)

This guide explains how to add **music-reactive and non-music LED effects** to DeskBuddy
without breaking the existing firmware/backend. It borrows concepts from
[WLED](https://github.com/wled/WLED) (effects engine, segments, usermods, AudioReactive)
while keeping DeskBuddy's current OLED/TFT/sensor stack intact.

Reference repository: https://github.com/wled/WLED

---

## 1. Integration strategies

### Strategy A — External WLED bridge (zero firmware risk, recommended first)
Run WLED on a **separate ESP32** (or ESP8266) that drives the LED strip. DeskBuddy's
backend pushes state to WLED over the network:

- WLED JSON API: `POST http://<wled-ip>/json/state` with `{"seg":[{"fx":..,"col":[[r,g,b]]}]}`
- Or UDP realtime (E1.31 / Art-Net / DDP) for low-latency music sync
- Or MQTT topics that both devices share

DeskBuddy firmware is **not touched**. Music reactivity can be driven by backend
music state (playing/paused, progress) and/or a mic attached to the WLED device
(WLED's AudioReactive usermod).

### Strategy B — Native LED module in DeskBuddy firmware (optional, guarded)
Add a WS2812B (or compatible) strip directly to the ESP32-S3 and a small,
non-blocking effects engine. All new code is isolated and disabled by default via
`#if defined(ENABLE_LED_STRIP)` so existing builds are unchanged.

---

## 2. Non-breaking rules

1. **Feature flag**: wrap all new code in `#if defined(ENABLE_LED_STRIP)`. Default build does not define it.
2. **One hook point**: add a single `ledUpdate(millis())` call inside the main loop,
   guarded by the flag. No edits to existing sensor/UI functions.
3. **No blocking calls**: effects use `millis()` scheduling; never `delay()` in the loop.
4. **Optional hardware**: if init fails or no strip, set `ledOk = false` and skip silently.
5. **Config in NVS/JSON**: pin, LED count, brightness, effect, palette stored as settings;
   defaults keep feature off.
6. **Backend additive only**: new endpoints (`/api/v1/led/*`) must not alter existing routes.
7. **Serial protocol additive**: new command `{"cmd":"led",...}`; unknown commands already ignored.

---

## 3. Suggested new firmware files (Strategy B)

```
firmware/arduino/DeskBuddy_Companion/
  DeskBuddy_Companion.ino        # +1 guarded hook in loop()
  led_effects.h                  # effects + segment state (new)
  led_effects.cpp                # (or .ino tab) implementation
```

Minimal integration in `.ino`:
```cpp
#if defined(ENABLE_LED_STRIP)
#include "led_effects.h"
#endif

// in setup():
#if defined(ENABLE_LED_STRIP)
  ledInit();   // uses PIN_LED_DATA, LED_COUNT from config; sets ledOk
#endif

// in loop():
#if defined(ENABLE_LED_STRIP)
  if (ledOk) ledUpdate(millis());
#endif
```

---

## 4. Music + non-music effects

**Music-reactive (inputs: mic RMS from INMP441, backend music state)**
- VU meter (brightness follows `sensors.micLevel`)
- Spectrum-ish bars (bucket mic samples; optional FFT)
- Beat pulse (threshold on RMS delta → flash)
- Color from album art / activity (backend sends `led_color`)
- Idle breathing when music paused

**Non-music (time/ambient driven)**
- Solid color, rainbow, breathing, comet, fire, twinkle, chase, gradient, color wipe
- Status indicator (battery low = red, inspection fault = alarm red, etc.)
- Activity themes (coding = blue, gaming = purple, etc.)
- Segment support (different effects per region, WLED-style)

Switching between music and non-music is automatic: if `state.musicPlaying` → music
effects; else → ambient/status effects. Manual override via command.

---

## 5. Hardware pin connections

### Existing DeskBuddy (unchanged)
| Component | Pins |
|---|---|
| I2C (SDA/SCL) | GPIO 8 / 9 |
| SH1106 OLED 128×64 | @0x3C |
| BME280 | @0x77 (0x76 fallback) |
| ADXL345 | @0x53 |
| ST7735 TFT (SPI) | CS=10, MOSI=11, SCLK=12, DC=13, RST=14, BL=15 |
| Buttons (active LOW) | MODE=16, VOICE=17, UP=19, DOWN=18, SELECT=4 |
| Speaker (PWM) | GPIO 21 |
| Battery ADC | GPIO 1 |
| I2S Mic (INMP441) | SCK=5, WS=6, SD=7 |

### New LED output (Strategy B) — recommended
| Signal | GPIO | Notes |
|---|---|---|
| LED data (WS2812B/NeoPixel, 16 LEDs) | **GPIO 48** | ARGB ring/strip. Use 300–500 Ω series resistor. |
| Alt data pin | GPIO 2 | If GPIO 48 is unavailable |
| Extra strips (optional) | GPIO 39–42, 47 | One RMT channel per output |

Avoid: GPIO 0,3,45,46 (strapping), 19/20 (USB), 26–32 (flash), 33–37 (PSRAM),
and any already-used pins above.

### Wiring notes
- Power LED strip from **external 5 V** (not ESP32 3V3/5V pin) for >8 LEDs.
- Common GND between ESP32 and strip power supply.
- 3.3 V → 5 V level shifter recommended for long strips; many strips work direct on short runs.
- 1000 µF electrolytic across strip 5 V/GND.
- Keep data wire short; add series resistor at ESP32 end.

### WLED device pins (Strategy A, separate board)
Configure in WLED settings. Typical ESP32 defaults are LED data on GPIO 2 and I2S mic
pins per your board; verify against the specific WLED-supported board profile. Do not
reuse DeskBuddy's pins if both share one ESP32.

---

## 6. Backend additions (additive)

- `app/services/led.py`: store LED settings, compute effect from activity/music.
- `app/api/v1/led.py`: GET/PUT settings, POST effect/color, POST music-reactive toggle.
- WebSocket/serial dispatch: send `{"cmd":"led","effect":..,"color":..,"brightness":..}`.
- Web panel: new "LED" tab or section in Device Theme.

---

## 7. Minimal serial commands

```
{"cmd":"led","power":true}
{"cmd":"led","effect":"rainbow","speed":128,"brightness":200}
{"cmd":"led","mode":"music"}          // music-reactive
{"cmd":"led","mode":"ambient"}       // non-music
{"cmd":"led","color":"#FF00AA"}
```

---

## 8. Testing / safety checklist

- Build with and without `ENABLE_LED_STRIP`; both must compile.
- If strip disconnected, firmware must not crash (guard all LED calls).
- Existing 41 backend tests remain green; add LED service tests separately.
- Confirm no change to TFT/OLED frame timing (LED update < 1 ms).

---

## 9. WLED concepts to borrow

- Effect functions as small, stateful generators (see WLED `FX.cpp`).
- Segment abstraction for multi-region strips.
- Usermod pattern for optional features (compile-time flags).
- AudioReactive: FFT + beat detection feeding effect parameters.

Do **not** replace DeskBuddy firmware with WLED; integrate via API/bridge or a
guarded native module as above.
