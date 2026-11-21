# 🤖 DeskBuddy — Industrial Inspection & Desk Companion

> **Dual-mode intelligent device: AI-powered industrial vibration inspection + PC-aware desk companion.**
> Built on ESP32-S3 N16R8, driven by a unified Python backend with a React web control panel.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Two Modes](#two-modes)
- [Hardware](#hardware)
- [Architecture](#architecture)
- [Features](#features)
- [Quick Start](#quick-start)
- [Web Control Panel](#web-control-panel)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Roadmap & Future Proposals](#roadmap--future-proposals)
- [License](#license)

---

## Overview

DeskBuddy is a single ESP32-S3 device that switches between two personalities:

1. **Desk Buddy mode** — A PC-aware desk companion with an expressive OLED face, TFT dashboard, music/lyrics, notifications, Pomodoro, battery/mic telemetry, gaming mode, and a customizable device theme.
2. **Industrial Inspection mode** — A handheld vibration/acoustic analyzer that captures sensor data, runs a CNN + traditional analysis pipeline on a backend, and reports equipment health & Remaining Useful Life (RUL).

A single backend (`deskbuddy_backend`) serves both modes over serial, WebSocket, and REST. A React web panel (single HTML file, no Node.js needed) provides full control.

---

## Two Modes

### 🖥️ Desk Buddy Mode
PC-aware companion that reacts to your activity (coding, browsing, gaming, watching), shows system metrics, plays music with synced lyrics, receives notifications, and runs Pomodoro. Expressive OLED eyes change with mood/activity. Gestures (tap, shake) control the UI.

### 🔧 Industrial Inspection Mode
Handheld analyzer for motor/bearing fault diagnosis:
- ADXL345 vibration capture (100 samples @ ~40 Hz)
- CNN model (PyTorch, 38 MB, 100% accuracy on CWRU dataset) + traditional FFT analysis
- ISO 10816-3 vibration severity classification (Zone A–D)
- Equipment age tracking + RUL (Remaining Useful Life) projection
- Prognostics engine: exponential degradation model → "will stop working in N days"

Switch modes with the **MODE button** or via web panel / API.

---

## Hardware

### ESP32-S3 N16R8 (known-good wiring)

| Component | Pins |
|-----------|------|
| I2C (SDA/SCL) | GPIO 8 / 9 |
| SH1106 OLED 128×64 | @0x3C |
| BME280 | @0x77 (0x76 fallback) |
| ADXL345 | @0x53 |
| ST7735 TFT (SPI) | CS=10, MOSI=11, SCLK=12, DC=13, RST=14, BL=15 |
| Buttons (active LOW) | MODE=16, VOICE=17, UP=19, DOWN=18, SELECT=4 |
| Speaker (PWM) | GPIO 21 |
| Battery ADC | GPIO 1 |
| I2S Mic (INMP441) | SCK=5, WS=6, SD=7 |

### Requirements
- Arduino IDE with ESP32 board package
- Libraries: U8g2, Adafruit GFX, Adafruit ST7735, Adafruit BME280, Adafruit ADXL345, ArduinoJson v7, ESP_I2S
- Python 3.11+ with conda env `inspection`
- (Optional) NVIDIA GPU for ML inference

---

## Architecture

```
┌─────────────────┐     Serial/USB      ┌──────────────────────┐
│  ESP32-S3       │ ◄────────────────► │  deskbuddy_backend   │
│  (OLED + TFT)   │   115200 baud      │  (FastAPI + SQLite)  │
│  Sensors/Mic    │   JSON lines       │  PC monitoring       │
└─────────────────┘                    │  Music/Lyrics        │
                                       │  ML (CNN + trad.)    │
                                       │  Prognostics (RUL)   │
                                       └──────────┬───────────┘
                                                  │
                                       ┌──────────┴───────────┐
                                       │  Web Control Panel   │
                                       │  (React, single HTML)│
                                       │  http://127.0.0.1:8080│
                                       └──────────────────────┘
```

```
multimodel_inspection_desk_buddy/
├── firmware/arduino/DeskBuddy_Companion/   # Arduino IDE sketch (flash this)
├── deskbuddy_backend/                      # Unified API/DB service
│   ├── app/
│   │   ├── api/v1/        # REST endpoints (system, vibration, device, companion, gaming, config, voice)
│   │   ├── services/      # companion, music, lyrics, vibration, gaming, prognostics, cover_art, voice
│   │   └── main.py        # FastAPI app + lifespan
│   ├── web/index.html     # React control panel (9 tabs)
│   └── tests/             # 41 pytest tests
├── desktop_bridge/        # Separate desktop companion service
├── ml/                    # CNN model training (CWRU dataset)
└── models/                # Trained model (cnn_model.pth, 38MB)
```

---

## Features

### ✅ Desk Buddy Mode
- **OLED face** — 25+ expressions, blinking, pupil tracking via accelerometer
- **TFT dashboard** — 8 pages (Home, Music, Lyrics, PC, Environment, Notifications, Pomodoro, Inspection) with partial refresh
- **PC telemetry** — CPU/GPU/RAM/temp, foreground app, idle time, clock
- **Music** — now-playing, play/pause (SMTC), progress interpolation for backgrounded tabs
- **Synced lyrics** — LRCLIB with LRC parser, cache, full sheet, UNSYNCED badge
- **Cover art** — iTunes resolution, 40×40 thumbnail (ESP32) + blurred background (lyrics page), web backdrop
- **Gestures** — single tap (wake), double tap (music), triple tap (voice), shake (home + surprised)
- **Notifications** — push from backend, priority levels, queue (8 slots)
- **Pomodoro** — work/break timer with notifications
- **Battery** — 3S Li-ion piecewise curve, USB-power detection, percent
- **Microphone** — I2S RMS level meter
- **Gaming mode** — process detection, session tracking, temp/VRAM alerts
- **Device theme** — 12 colors/sizes, instant apply, partial refresh on all pages
- **System monitor** — GPU: NVML→nvidia-smi→WMI; CPU temp: psutil→LHM/OHM→ACPI
- **Autonomous mode** — face stays alive when PC link drops

### ✅ Industrial Inspection Mode
- **CNN vibration analysis** — PyTorch model, 100% accuracy on CWRU dataset
- **Traditional analysis** — FFT, envelope, ISO 10816-3 classification
- **Equipment prognostics (RUL)** — age tracking, exponential degradation, failure date projection
- **ISO 10816-3 zones** — Zone A (Good) → Zone D (Critical)
- **Inspection TFT page** — live accel, capture buffer, result display
- **Cover art & blurred backgrounds** for inspection reports (planned)

### ✅ Web Control Panel (9 Tabs)
Dashboard · Expressions · Buttons · Notifications · Sensor Graphs · Inspection · Gaming · Theme · Device Theme · Settings

### ✅ Backend API
- 40+ REST endpoints, WebSocket channels, serial dispatch
- 41 pytest tests (all passing)
- SQLite/PostgreSQL, Redis (optional), Docker support

---

## Quick Start

### 1. Backend
```bash
cd deskbuddy_backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env   # edit COM port, API keys, etc.
python -m app.main
```
- API: http://127.0.0.1:8080
- Docs: http://127.0.0.1:8080/docs
- Web panel: http://127.0.0.1:8080/

### 2. Firmware (Arduino IDE)
1. Open `firmware/arduino/DeskBuddy_Companion/DeskBuddy_Companion.ino`
2. Board: **ESP32S3 Dev Module**, Flash 16MB, PSRAM OPI, Partition 3MB APP/9.9MB FATFS
3. Install libraries: U8g2, Adafruit GFX, Adafruit ST7735, Adafruit BME280, Adafruit ADXL345, ArduinoJson v7
4. Upload to COM port

### 3. Connect
- Web panel → **Settings** → **Connect Device**
- Or: `POST http://127.0.0.1:8080/api/v1/device/connect`

### 4. Run Tests
```bash
cd deskbuddy_backend
pytest tests/ -q   # 41 passed
```

---

## Web Control Panel

| Tab | Function |
|-----|----------|
| Dashboard | Live metrics, device status, now-playing with cover art |
| Expressions | Trigger OLED expressions remotely |
| Buttons | Simulate device button presses |
| Notifications | Send notifications to device |
| Sensor Graphs | Battery, mic, accel, temp charts |
| Inspection | Vibration capture, CNN analysis, RUL prognostics |
| Gaming | Game detection, session tracking, alerts |
| Theme | Web app theme (CSS variables) |
| Device Theme | Push colors/fonts to ESP32 TFT |
| Settings | Serial connect/disconnect, intervals, lyrics offset |

---

## API Reference

| Category | Endpoint | Description |
|----------|----------|-------------|
| System | `GET /api/v1/system/metrics` | Current PC metrics |
| Inspection | `POST /api/v1/inspect/vibration` | Analyze vibration (CNN + traditional) |
| | `GET /api/v1/inspect/prognostics/{motor_id}` | Equipment RUL & health |
| Device | `POST /api/v1/device/connect` | Connect serial |
| | `POST /api/v1/device/mode` | Switch mode |
| | `POST /api/v1/device/command` | Send raw command |
| Companion | `GET /api/v1/companion/device-state` | Flat serial state packet |
| Desktop | `GET /api/v1/desktop/music/status` | Music status + album art |
| | `GET /api/v1/desktop/music/lyrics` | Current 3-line lyric window |
| | `GET /api/v1/desktop/music/lyrics/full` | Full cached lyric sheet |
| Config | `GET/PUT /api/v1/config/device-theme` | Device theme |
| Voice | `POST /api/v1/voice/query` | Voice assistant query |

Full interactive docs: http://127.0.0.1:8080/docs

---

## Roadmap & Future Proposals

### 🚀 Proposed Future Updates

#### 1. Voice Assistant (In Progress)
- **Status:** Nemotron LLM integration, tool calling scaffolded
- **Next:** Push-to-talk via VOICE button → STT → LLM → TTS → speaker
- **Proposal:** Add wake word detection ("Hey Buddy"), offline STT (Whisper.cpp on ESP32-S3), streaming responses

#### 2. Charging Detection
- **Status:** Not implemented (no charge-detect pin)
- **Proposal:** Infer charging state from voltage trend (rising = charging) + USB VBUS detection via ADC. Add `batt_chg` field updates.

#### 3. Alarm & Stopwatch
- **Status:** Out of scope (original spec)
- **Proposal:** Timer/alarm on Pomodoro page, countdown with beep, stopwatch with lap times. Store in NVS for persistence.

#### 4. Music Visualizer
- **Status:** Out of scope
- **Proposal:** FFT-based visualizer on TFT using mic input (I2S). Bar graph / waveform synchronized to audio. Low priority (CPU intensive on ESP32).

#### 5. Album Art on Device (Enhanced)
- **Status:** 40×40 thumbnail + blurred background working
- **Proposal:** Higher resolution (80×80) with PSRAM, animated transitions between tracks, color extraction for dynamic theme

#### 6. Multi-Device Support
- **Status:** Single device only
- **Proposal:** Support multiple ESP32 devices (desk + workshop), device registry in backend, per-device themes and state

#### 7. OTA Firmware Updates
- **Status:** Manual Arduino IDE flash
- **Proposal:** ESP32 OTA via backend (upload .bin, device pulls and flashes). Critical for deployed inspection units.

#### 8. Inspection Report Generation
- **Status:** Vibration analysis + RUL computed
- **Proposal:** PDF report generation with charts, ISO compliance certificate, email delivery. Integrate with CMMS systems.

#### 9. Edge ML on Device
- **Status:** CNN runs on backend (PC)
- **Proposal:** Quantize model (INT8) and run on ESP32-S3 with TensorFlow Lite Micro. Enables offline inspection without PC.

#### 10. Battery Optimization
- **Status:** Always-on
- **Proposal:** Deep sleep between inspections, wake on button/accelerometer, solar charging support for field units.

#### 11. Cloud Sync
- **Status:** Local only
- **Proposal:** Optional cloud backup of inspection reports, device telemetry, music preferences. Multi-tenant support.

#### 12. Accessibility
- **Status:** Not considered
- **Proposal:** High-contrast theme, larger fonts, voice feedback for visually impaired users, screen reader support in web panel.

---

## License

MIT License — See LICENSE file for details.

---

## Acknowledgments

Built with inspiration from:
- **DeskMate** — expressive desk companion
- **deskey-v2** — PC activity & sleep engine
- **StatNode** — compact PC metrics dashboard
- **yt-music-companion** — now-playing screen
- **Hermes** — push-to-talk voice button