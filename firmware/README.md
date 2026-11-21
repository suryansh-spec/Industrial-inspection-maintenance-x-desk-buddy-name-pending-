# ESP32 Firmware - Dual-Mode Inspection Desk Buddy

> **Using the ESP32-S3 N16R8?** This PlatformIO tree is the legacy
> ESP32-classic prototype. Flash the Arduino IDE sketch in
> [`firmware/arduino/DeskBuddy_Companion/`](arduino/DeskBuddy_Companion/)
> instead. That sketch uses the verified S3 wiring (I2C on GPIO8/9, TFT on
> GPIO10-15, buttons, I2S mic, and the backend serial protocol). The pin table
> below applies only to the old board.

## Overview
Firmware for the ESP32-based dual-mode device implementing PRD v2.0.

**Current Phase:** Phase 0/1 - Core Firmware Foundation

## Hardware (from pin_assingment.txt)
| Component | Pins |
|-----------|------|
| ST7735 TFT | SPI: SCK=18, MOSI=23, CS=13, DC=14, RST=27, BL=2 |
| MPU6050 | I²C: SDA=21, SCL=22, INT=39 |
| ADXL345 | I²C: SDA=21, SCL=22, INT1=35 |
| INMP441 | I²S: SCK=26, WS=25, SD=34 |
| SmartElex Speaker | PWM: GPIO33 |
| 5 Buttons | MODE=16, VOICE=17, UP=19, DOWN=32, SELECT=4 |
| Battery ADC | GPIO36 (VP) |
| Probe Detect | GPIO39 (VN) |

## Project Structure
```
firmware/
├── platformio.ini          # PlatformIO config with lib_deps
├── include/
│   └── pin_config.h        # Centralized pin definitions
├── lib/
│   └── TFT_eSPI/
│       └── User_Setup.h    # ST7735 config for 135x240 display
└── src/
    ├── main.cpp            # Entry point, mode switching, main loop
    ├── globals.h           # Global instance declarations
    ├── core/
    │   ├── mode_manager.h/.cpp     # Mode state machine (Inspection/Desk Buddy)
    │   ├── state_manager.h/.cpp    # Activity state machine (PRD §3.3)
    │   ├── task_manager.h/.cpp     # FreeRTOS task coordination
    │   └── config_manager.h/.cpp   # NVS persistence
    ├── hardware/
    │   ├── display_driver.h/.cpp   # ST7735 screens for both modes
    │   ├── button_driver.h/.cpp    # Debounced 5-button handling
    │   ├── mpu6050_driver.h/.cpp   # (placeholder)
    │   ├── adxl345_driver.h/.cpp   # (placeholder)
    │   ├── inmp441_driver.h/.cpp   # (placeholder)
    │   ├── smex_speaker.h/.cpp     # (placeholder)
    │   └── battery_monitor.h/.cpp  # (placeholder)
    ├── services/
    │   ├── wifi_manager.h/.cpp     # Wi-Fi STA/AP, reconnection
    │   ├── sensor_manager.h/.cpp   # MPU6050, ADXL345, BME280
    │   └── audio_manager.h/.cpp    # (placeholder)
    └── modes/
        ├── industrial/             # (Phase 2+)
        └── desk_buddy/             # (Phase 2+)
```

## Building

### Prerequisites
- PlatformIO Core (`pip install platformio`)
- ESP32 Arduino core (auto-installed by PlatformIO)

### Compile
```bash
cd firmware
pio run
```

### Upload
```bash
pio run --target upload
```

### Monitor Serial
```bash
pio device monitor --baud 115200
```

## Current Features (Phase 0/1)

✅ **Mode Management**
- Two modes: `INDUSTRIAL_INSPECTION` / `DESK_BUDDY`
- Physical button (GPIO16) switches modes without reboot
- Mode persisted in NVS across power cycles
- Clean transition: stop tasks → release resources → switch → start tasks → render home

✅ **State Management** (PRD §3.3)
- `BOOTING` → `READY` → `MODE_TRANSITION` → activity states
- Valid transition enforcement

✅ **Display Driver** (ST7735 135x240 landscape)
- **Desk Buddy Screens:** Home, Music, PC Monitor, Environment, Calendar, Assistant, Settings
- **Inspection Screens:** Home, Select Type, Setup, Live Acquisition, Analysis, Results
- Header with WiFi/battery, footer with button hints

✅ **Button Manager**
- 5 buttons with debouncing (25ms)
- Short press, long press (500ms), repeat (200ms), release events
- INPUT_PULLUP, active LOW

✅ **Sensor Manager**
- **MPU6050:** Accel/gyro/temp, gesture detection (tap, double-tap, shake)
- **ADXL345:** Vibration capture (configurable rate/duration, buffered)
- **BME280:** Environmental readings (optional)
- **Battery:** Voltage divider on GPIO36, percentage estimation

✅ **Wi-Fi Manager**
- STA mode with saved credentials (NVS)
- Automatic reconnection (30s interval)
- AP fallback for initial config
- Event-driven status callbacks

✅ **Config Manager** (NVS)
- Active mode, Wi-Fi credentials
- Brightness, time format, volume
- Device ID, inspection configs

## Next Phases

### Phase 2: Desk Buddy MVP
- Clock/NTP, timers/alarms
- MPU6050 gestures → UI actions
- Desktop bridge communication (HTTP/WS)
- PC monitoring, calendar, music metadata display

### Phase 3: Industrial Inspection
- ADXL345 vibration capture → feature extraction → upload
- INMP441 acoustic capture
- Inspection data model, equipment profiles

### Phase 4: Voice Assistant
- Push-to-talk (voice button)
- INMP441 → STT → Nemotron → TTS → SmartElex speaker
- Tool registry (music, calendar, PC, device, inspection)

## Pin Validation
Compile-time checks in `pin_config.h`:
- Input-only GPIOs (34-39) not used for output
- Boot-strap pins (0,2,5,12,15) avoided
- I²C addresses defined for all sensors

## Memory Management (PRD §10.3)
- Fixed-size buffers for vibration capture
- FreeRTOS tasks with bounded stacks
- No dynamic allocation in hot paths
- Display assets kept minimal