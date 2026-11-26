# Omnipect Backend

Unified backend for the **Industrial Inspection & Desk Companion** system.

Integrates features from:
- **DeskMate** - Desktop companion with notifications, Pomodoro, quick actions
- **deskey-v2** - Keyboard/macro mapping with layers
- **Hermes** - Multi-channel notification delivery
- **StatNode** - System monitoring with alerting
- **yt-music-companion** - YouTube Music integration

## Architecture

```
deskbuddy_backend/
├── app/
│   ├── api/v1/           # REST API endpoints
│   │   ├── system.py     # System metrics & alerts (StatNode)
│   │   ├── vibration.py  # Vibration analysis (ML + Traditional)
│   │   ├── device.py     # Device management
│   │   ├── desktop_tools.py  # PC, Music, Calendar, Notifications
│   │   └── voice.py      # Voice assistant (Nemotron)
│   ├── core/
│   │   ├── config.py     # Configuration management
│   │   ├── database.py   # Database setup
│   │   ├── security.py   # Auth & JWT
│   │   └── events.py     # Event bus
│   ├── services/
│   │   ├── system_monitor.py    # StatNode-style monitoring
│   │   ├── notification_service.py  # Hermes-style notifications
│   │   ├── music.py             # yt-music-companion integration
│   │   ├── calendar.py          # Google/Outlook calendar
│   │   ├── voice.py             # Nemotron voice assistant
│   │   ├── hardware_bridge.py   # Arduino/ESP32 serial bridge
│   │   ├── deskmate.py          # DeskMate features
│   │   └── pc_monitor.py        # System monitoring
│   ├── models/           # SQLAlchemy models
│   └── api/              # API routes
├── alembic/              # Database migrations
├── tests/                # Tests
├── docker-compose.yml    # Full stack deployment
├── Dockerfile            # Container image
├── pyproject.toml        # Package config
├── requirements.txt      # Dependencies
└── README.md
```

## Features

### 🔧 System Monitoring (StatNode)
- Real-time CPU, RAM, GPU, Disk, Network metrics
- Historical data with configurable retention
- Alert rules with conditions and thresholds
- Multi-channel alerting (email, webhook, push, WebSocket)
- Prometheus-compatible metrics

### 🔔 Notifications (Hermes)
- Multi-channel: Email, Webhook, Push, SMS, In-App, WebSocket, DeskMate
- Priority levels: Low, Normal, High, Urgent
- Template system with variables
- Action buttons for interactive notifications
- Delivery tracking and retries

### 🎵 Music Control (yt-music-companion)
- Cross-platform: Windows, macOS, Linux
- YouTube Music API integration
- Playback control: play, pause, next, previous, volume
- Search and queue management
- Lyrics fetching

### 🎹 Keyboard/Macros (deskey-v2)
- Multi-layer key mappings
- Macro recording and playback
- Layer switching (momentary, toggle)
- OLED display support
- RGB lighting control

### 🖥️ DeskMate Desktop Companion
- System tray integration (Windows, macOS, Linux)
- Notification center with history
- Pomodoro timer with notifications
- Quick actions with hotkeys
- Clipboard history
- Overlay widget
- System tray integration

### 🔧 Hardware Bridge (Arduino/ESP32)
- Serial communication with Arduino/ESP32
- Sensor data: ADXL345, BME280, custom
- Display management: ST7735, SH1106 OLED
- Pomodoro timer on device
- Notifications on device display
- Inspection workflow trigger

### 🧑‍💻 DeskBuddy Companion
- 1 Hz PC-aware state: activity, expression, sleep stage, clock, media
- GPU utilization, VRAM, temperature and fan through NVML, with an
  `nvidia-smi` fallback and WMI name/VRAM as the last resort
- CPU temperature through `psutil`, LibreHardwareMonitor/OpenHardwareMonitor,
  or the ACPI thermal zone (exposed separately as `thermal_zone_c`)
- ADXL345 gestures: single/double/triple tap and shake
- LRCLIB synced lyrics with plain-text fallback and a per-track cache
- Battery voltage/percentage and I2S microphone level in device telemetry

### 🤖 Voice Assistant (Nemotron)
- Push-to-talk → Wi-Fi HTTP → faster-whisper STT (`tiny.en`, local CPU) → NVIDIA Nemotron LLM (`nvidia/nemotron-3-ultra-550b-a55b`) → edge-tts TTS → 16 kHz PCM WAV
- Multi-turn conversation history (NVS-backed on device; in-memory on backend)
- Tool calling: motor inspection, equipment RUL, media control, buddy expressions
- Reasoning disabled via `chat_template_kwargs: {"enable_thinking": false}`
- Windows SAPI offline TTS fallback; `/chat`, `/chat/json`, `/tts`, `/stt`, `/health`, `/ws`, `/reset`, `/status`, `/tools`
- E2E verified end-to-end (~15 s per turn); 51 voice tests pass

### 🎵 YouTube Music Integration
- Search and playback control
- Lyrics fetching
- Queue management
- Cross-platform support

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- (Optional) NVIDIA GPU for ML inference
- Arduino/ESP32 with sensors

### Installation

```bash
# 1. Clone and enter directory
cd deskbuddy_backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your settings

# 5. Initialize database
# Tables are created automatically on startup via app.core.database.init_db()
# (alembic upgrade head is a no-op until migration revisions are added)

# 6. Run development server
python -m app.main
```

### With Docker

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f deskbuddy-backend

# Train ML model
docker-compose --profile training up ml-train
```

## Configuration

Key environment variables (`.env`):

```ini
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/deskbuddy

# Supabase note: the direct host (db.<ref>.supabase.co) is IPv6-only.
# On IPv4-only networks use the Session pooler string instead:
# DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

# Redis
REDIS_URL=redis://localhost:6379/0

# Serial (Arduino/ESP32)
SERIAL_PORT=COM3
SERIAL_BAUDRATE=115200

# Backend API
BACKEND_URL=http://localhost:8000

# ML Model
ML_MODEL_PATH=ml/.../models/cnn_model.pth

# Voice Assistant
NVIDIA_API_KEY=your_key_here

# Features
ENABLE_PC_MONITORING=true
ENABLE_MUSIC_CONTROL=true
ENABLE_CALENDAR=true
ENABLE_VOICE_ASSISTANT=true
ENABLE_DESK_MATE=true
```

## API Endpoints

| Category | Endpoint | Description |
|----------|----------|-------------|
| **System** | `GET /api/v1/system/metrics` | Current metrics |
| | `GET /api/v1/system/metrics/history` | Historical data |
| | `GET /api/v1/system/alerts` | Active alerts |
| | `POST /api/v1/system/alerts/rules` | Create alert rule |
| **Inspection** | `POST /api/v1/inspect/vibration` | Analyze vibration |
| | `GET /api/v1/inspect/methods` | List methods |
| **Device** | `GET /api/v1/device/status` | Device status |
| | `GET /api/v1/device/ports` | List serial ports |
| | `POST /api/v1/device/connect` | Connect to the device |
| | `POST /api/v1/device/mode` | Switch mode |
| **Companion** | `GET /api/v1/companion/context` | Full PC context |
| | `GET /api/v1/companion/summary` | Compact companion state |
| | `GET /api/v1/companion/device-state` | Flat serial state packet |
| **Desktop** | `GET /api/v1/desktop/pc/metrics` | PC metrics |
| | `POST /api/v1/desktop/music/play` | Play music |
| | `GET /api/v1/desktop/music/lyrics` | Current 3-line lyric window |
| | `GET /api/v1/desktop/music/lyrics/full` | Full cached lyric sheet |
| | `GET /api/v1/desktop/calendar/events` | Calendar events |
| **Voice** | `POST /api/v1/voice/chat` | STT → Nemotron → TTS, returns 16 kHz WAV + `X-Transcript`/`X-Reply-Text` |
| | `POST /api/v1/voice/chat/json` | JSON variant of `/chat` |
| | `POST /api/v1/voice/tts` | Text → 16 kHz PCM WAV |
| | `POST /api/v1/voice/stt` | Transcribe WAV/MP3 → text |
| | `GET /api/v1/voice/health` | Voice service probe |
| | `GET /api/v1/voice/status` | Voice config/status |
| | `POST /api/v1/voice/reset` | Clear conversation history |
| | `WS /api/v1/voice/ws` | Real-time voice (WAV in, WAV out) |
| | `GET /api/v1/voice/tools` | List Nemotron tools |

## WebSocket Channels

| Channel | Events |
|---------|--------|
| `deskbuddy_state` | Full 1 Hz companion state (lyrics, battery, microphone) |
| `activity` | Activity, expression and sleep-stage changes |
| `sensor_data` | Real-time sensor readings |
| `gesture` | Single/double/triple tap and shake events |
| `device_event` | Raw device events (buttons, gestures, mode changes) |
| `pc_metrics` | PC metrics updates |
| `notifications` | New notifications |
| `pomodoro` | Pomodoro timer events |
| `serial_data` | Raw serial data |
| `heartbeat` | Keep-alive |

## Hardware Integration

### Arduino/ESP32 Protocol
```json
// Device → Bridge
{"type": "sensor_data", "data": {
  "accel": {"x": 0.1, "y": 0, "z": 9.8},
  "temp": 23.5, "humidity": 48.0, "pressure": 1012.5,
  "battery": 11.8, "battery_pct": 72, "mic_level": 34
}}
{"type": "gesture", "gesture": "double_tap", "page": "music"}

// Bridge → Device
{"cmd": "deskbuddy_state", "payload": {
  "act": "coding", "expr": "coding", "sleep": "active",
  "lyr_prev": "...", "lyr_cur": "...", "lyr_next": "...",
  "batt": 72, "batt_v": 11.8, "batt_chg": -1, "mic": 34
}}
{"cmd": "mode_switch", "payload": {"mode": "inspection"}}
{"cmd": "page", "payload": {"page": 2}}
```

Lyrics come from LRCLIB (`/api/get`, then `/api/search`), with synced LRC
preferred and plain lyrics shown statically. Lookups are cached per track, so
the 1 Hz state path does not issue network calls.

## ML Pipeline

Train the CNN model:
```bash
cd ml/signal_fault_classification_pipeline/signal-fault-classification
python train_pipeline.py --epochs 50
```

Deploy model:
```bash
cp models/cnn_model.pth deskbuddy_backend/models/
```

## Development

```bash
# Run tests
pytest tests/

# Format code
black .
ruff check .

# Type checking
mypy app/
```

## License

MIT License - See LICENSE file for details.