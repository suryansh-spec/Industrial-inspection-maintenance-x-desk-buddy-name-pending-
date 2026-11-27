# 🤖 Omnipect — Industrial Inspection & Desk Companion

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

Omnipect is a single ESP32-S3 device that switches between two personalities:

1. **Omnipect mode** — A PC-aware desk companion with an expressive OLED face, TFT dashboard, music/lyrics, notifications, Pomodoro, battery/mic telemetry, gaming mode, and a customizable device theme.
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
| Battery ADC | GPIO 1 |
| I2S Mic (INMP441) | SCK=5, WS=6, SD=7 |
| MAX98357A I2S Amp | BCLK=40, WS=41, DIN=42 |
| Speaker (via MAX98357A) | 2 W speaker on MAX98357A OUT+/OUT-
| Addressable LED ring (WS2812B, 16 LEDs) | Data=GPIO 4, ext 5 V + common GND |

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
- **Voice assistant** — push-to-talk (VOICE button) → Wi-Fi HTTP → faster-whisper STT → Nemotron LLM → edge-tts TTS → MAX98357A speaker (E2E working: STT→LLM→TTS→speaker). See `VOICE_ASSISTANT.md`.
- **Speaker** — MAX98357A I2S amplifier (BCLK=40, WS=41, DIN=42) driving 2 W speaker; boot beep, voice TTS output, and system alerts confirmed working.
- **LED ring** — WS2812B 16-LED ring on GPIO 4; RGB color control from web panel Device Theme page; confirms device state and notifications visually.
- **Microphone** — I2S RMS level meter
- **Gaming mode** — process detection, session tracking, temp/VRAM alerts
- **Device theme** — 12 colors/sizes, instant apply, partial refresh on all pages
- **System monitor** — GPU: NVML→nvidia-smi→WMI; CPU temp: psutil→LHM/OHM→ACPI
- **Autonomous mode** — face stays alive when PC link drops

### ✅ Industrial Inspection Mode
- **CNN vibration analysis** — Deep residual 1D-CNN (ExtensiveCNN-light + spectral branch), 100% accuracy on CWRU 4-class benchmark with recording-level splits (no leakage). GPU-accelerated (RTX 3060, CUDA 12.4). See `ml/bearing_fault_desk_buddy_updated/` for full research documentation.
- **Traditional analysis** — FFT, envelope, ISO 10816-3 classification (statistical fallback when CNN unavailable)
- **Equipment prognostics (RUL)** — Physics-informed multi-model RUL (exponential + linear + Paris' law crack growth), ISO 10816-3 severity (Zone A–D), uncertainty quantification, blended health index
- **ISO 10816-3 zones** — Zone A (Good) → Zone D (Critical)
- **Inspection TFT page** — live accel, capture buffer, result display, perimeter progress ring
- **Extended CWRU downloader** — 64 MAT files covering 12k/48k DE/FE, inner/ball/outer faults at 3 diameters × 4 loads
- **Cover art & blurred backgrounds** for inspection reports (planned)

### ✅ Web Control Panel (9 Tabs)
Dashboard · Expressions · Buttons · Notifications · Sensor Graphs · Inspection · Gaming · Theme · Device Theme · Settings

### ✅ Backend API
- 40+ REST endpoints, WebSocket channels, serial dispatch
- 41 pytest tests (all passing)
- SQLite/PostgreSQL, Redis (optional), Docker support

---

## Quick Start (Clone & Run on Any Laptop)

### Option A — One-Click Windows Setup & Launch
1. **Clone the repository:**
   ```bash
   git clone https://github.com/suryansh-spec/Industrial-inspection-maintenance-x-desk-buddy-name-pending-.git
   cd Industrial-inspection-maintenance-x-desk-buddy-name-pending-
   ```
2. **Run First-Time Setup:** Double-click **`Setup_Omnipect.bat`**
   - Automatically creates `deskbuddy_backend/.env` from `.env.example` and `firmware/arduino/DeskBuddy_Companion/voice_config.h` from `voice_config.example.h`.
   - Auto-discovers your Conda `inspection` environment or creates a local `.venv` and installs all dependencies from `deskbuddy_backend/requirements.txt`.
3. **Add Your API Key:** Open `deskbuddy_backend/.env` and set `NVIDIA_API_KEY=nvapi-...` (for Nemotron Voice Agent).
4. **Launch Omnipect:** Double-click **`Start_Omnipect.bat`** (or **`Start_Omnipect_Silent.vbs`** for background mode).
   - Opens the Web Control Panel automatically at **http://127.0.0.1:8080/**
   - Auto-detects the ESP32-S3 USB COM port when plugged in.

### Option B — Manual CLI Setup (venv or Conda)
```bash
# Using Conda:
conda env create -f environment.yml
conda activate inspection

# Or using Python venv:
cd deskbuddy_backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

cp .env.example .env    # Edit NVIDIA_API_KEY
python -m app.main
```
- **Web Dashboard & Voice Agent:** http://127.0.0.1:8080/
- **Swagger API Docs:** http://127.0.0.1:8080/docs

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
| Voice | `POST /api/v1/voice/chat` | STT → Nemotron → TTS, returns 16 kHz WAV |
| | `POST /api/v1/voice/tts` | Text → 16 kHz PCM WAV |
| | `POST /api/v1/voice/stt` | Transcribe WAV/MP3 → text |
| | `GET /api/v1/voice/health` | Voice service probe |

Full interactive docs: http://127.0.0.1:8080/docs

---

## ML / Industrial Inspection Module

The strengthened inspection pipeline lives in `ml/bearing_fault_desk_buddy_updated/` and is fully documented in its own `README.md`. Key contributions to the DeskBuddy project:

| Contribution | Description |
|-------------|-------------|
| **Fault Classification** | Deep residual 1D-CNN (ExtensiveCNN-light + spectral branch), 100% test accuracy on CWRU 4-class benchmark with recording-level splits (no leakage) |
| **RUL Prognostics** | Physics-informed (exponential + linear + Paris' law), ISO 10816-3 severity (Zone A–D), uncertainty quantification, blended health index |
| **Data Pipeline** | Extended CWRU downloader (64 MAT files cataloged, 40 downloaded), augmentation, overlapping windows, recording-level stratified splits |
| **GPU Inference** | CUDA 12.4 PyTorch on NVIDIA RTX 3060 for training and inference |
| **Research Artifacts** | 20 publication-quality visualizations (time, frequency, time-frequency domains, ROC/PR curves, confusion matrix) |

See `ml/bearing_fault_desk_buddy_updated/README.md` for the complete research documentation including methodology, results, limitations, and reproducibility instructions.

### 🚀 Proposed Future Updates

#### 1. Voice Assistant (Complete)
- **Status:** Push-to-talk → Wi-Fi HTTP → faster-whisper STT → Nemotron LLM → edge-tts TTS → MAX98357A speaker. E2E verified: transcript → sensible reply → playable WAV → speaker output in ~15 s. 51 backend tests pass.
- **Proposal:** Add wake word detection ("Hey Buddy"), offline STT (Whisper.cpp on ESP32-S3), streaming responses.

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

