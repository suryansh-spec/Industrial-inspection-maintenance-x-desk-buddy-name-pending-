# Desktop Bridge

Central integration layer for the **Industrial Inspection & Desk Buddy** system.

Connects:
- **Arduino/ESP32** (Serial/HTTP) → Hardware sensors & display
- **FastAPI Backend** → ML inference, data storage, API
- **ML Pipeline** → Local CNN + Traditional vibration analysis
- **Desktop Tools** → PC monitoring, Music, Calendar, Voice Assistant

## Architecture

```
┌─────────────────┐     Serial/HTTP      ┌──────────────────┐
│  Arduino/ESP32  │ ◄──────────────────► │  Desktop Bridge  │
│  (Sensors/Act)  │                      │  (FastAPI + WS)  │
└─────────────────┘                      └────────┬─────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
            ┌───────────────┐              ┌───────────────┐              ┌───────────────┐
            │  FastAPI      │              │  ML Pipeline  │              │  Desktop      │
            │  Backend      │              │  (CNN + Trad) │              │  Tools        │
            │  (API/DB)     │              │  (Local/Cloud)│              │  (PC/Music/   │
            └───────────────┘              └───────────────┘              │  Cal/Voice)   │
                                                                          └───────────────┘
```

## Quick Start

### Prerequisites
- Python 3.11+
- Arduino/ESP32 connected via USB
- (Optional) NVIDIA GPU for CNN inference
- (Optional) NVIDIA API key for Nemotron voice

### Installation

```bash
# 1. Clone and enter directory
cd desktop_bridge

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install package in editable mode
pip install -e .

# 5. Copy and configure environment
cp .env.example .env
# Edit .env with your settings (serial port, API keys, etc.)

# 6. Run
python run.py
```

### With Docker

```bash
# Build and run all services
docker-compose up -d

# View logs
docker-compose logs -f desktop-bridge

# Train ML model (with GPU)
docker-compose --profile training up ml-train
```

## Configuration

Edit `.env` file:

```ini
# Serial connection to Arduino/ESP32
SERIAL_PORT=COM3          # Windows: COM3, Linux: /dev/ttyUSB0
SERIAL_BAUDRATE=115200

# Backend API
BACKEND_URL=http://localhost:8000

# ML Model
ML_MODEL_PATH=ml/.../models/cnn_model.pth

# Voice Assistant (Nemotron)
NVIDIA_API_KEY=your_key_here

# Features
ENABLE_PC_MONITORING=true
ENABLE_MUSIC_CONTROL=true
ENABLE_CALENDAR=true
ENABLE_VOICE_ASSISTANT=true
```

## API Endpoints

### Inspection
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/inspect/vibration/analyze` | POST | Analyze vibration (auto/cnn/traditional) |
| `/api/v1/inspect/vibration/cnn` | POST | CNN only |
| `/api/v1/inspect/vibration/traditional` | POST | Traditional only |
| `/api/v1/inspect/vibration/methods` | GET | List methods |

### Device
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/device/status` | GET | Device connection status |
| `/api/v1/device/ports` | GET | List serial ports |
| `/api/v1/device/connect` | POST | Connect to device |
| `/api/v1/device/mode` | POST | Switch mode (inspection/desk_buddy) |
| `/api/v1/device/command` | POST | Send raw command |

### Desktop Tools
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/desktop/pc/metrics` | GET | PC metrics (CPU, RAM, GPU, etc.) |
| `/api/v1/desktop/pc/metrics/history` | GET | Historical metrics |
| `/api/v1/desktop/music/status` | GET | Music playback status |
| `/api/v1/desktop/music/play|pause|next|prev` | POST | Music control |
| `/api/v1/desktop/music/volume` | POST | Set volume |
| `/api/v1/desktop/calendar/events` | GET | Calendar events |
| `/api/v1/desktop/calendar/next` | GET | Next event |
| `/api/v1/desktop/notifications` | GET | Notifications |

### Voice Assistant
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/voice/query` | POST | Text query with tool calling |
| `/api/v1/voice/tts` | POST | Text-to-speech |
| `/api/v1/voice/stt` | POST | Speech-to-text |
| `/api/v1/voice/ws` | WS | Real-time voice WebSocket |
| `/api/v1/voice/tools` | GET | List available tools |

### WebSocket
```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.data);
};

// Subscribe to channels
ws.send(JSON.stringify({type: 'subscribe', channels: ['sensor_data', 'pc_metrics']}));

// Send device command
ws.send(JSON.stringify({type: 'device_command', command: 'mode_switch', payload: {mode: 'inspection'}}));
```

### Channel Types
| Channel | Description |
|---------|-------------|
| `sensor_data` | Real-time sensor readings |
| `pc_metrics` | PC performance metrics |
| `serial_data` | Raw serial output |
| `notifications` | System notifications |
| `heartbeat` | Keep-alive pings |

## Voice Assistant Tools

The Nemotron voice assistant has access to these tools:

| Tool | Description |
|------|-------------|
| `get_device_status` | Check device connection & sensors |
| `switch_device_mode` | Switch inspection/desk_buddy mode |
| `get_pc_metrics` | CPU, RAM, GPU, disk, network |
| `control_music` | Play, pause, next, prev, volume |
| `get_calendar_events` | Upcoming events |
| `run_inspection` | Start vibration analysis |
| `get_inspection_history` | Recent results |
| `set_volume` | System volume |
| `get_system_info` | OS, hardware info |

## Arduino/ESP32 Protocol

The bridge expects JSON commands over serial:

```json
// Device → Bridge
{"type": "sensor_data", "accel": {"x": 0.1, "y": 0.0, "z": 9.8}, "temp": 23.5, "humidity": 45}

// Bridge → Device
{"cmd": "mode_switch", "payload": {"mode": "inspection"}}
{"cmd": "start_inspection", "payload": {"method": "auto"}}
{"cmd": "get_sensors", "payload": {}}
```

## ML Pipeline Integration

The bridge uses the local CNN model for edge inference:

```python
from desktop_bridge.ml.local_analyzer import LocalVibrationAnalyzer

analyzer = LocalVibrationAnalyzer("models/cnn_model.pth")
result = await analyzer.analyze(x, y, z, fs=1000)
# Returns: {status, predicted_class, confidence, worst_axis, axis_results}
```

Falls back to backend API → traditional analysis if model unavailable.

## Development

### Run Tests
```bash
cd desktop_bridge
python -m pytest tests/ -v
```

### Code Style
```bash
black .
ruff check .
mypy .
```

### Add New Desktop Tool
1. Create service in `services/`
2. Add router in `api/`
3. Register in `main.py` lifespan
4. Add voice tool in `services/voice.py`

## Hardware Requirements

| Component | Specification |
|-----------|---------------|
| MCU | ESP32-S3 N16R8 (Arduino IDE) |
| Display | ST7735 1.4" SPI + SH1106 OLED |
| Sensors | ADXL345 (I2C), BME280 (I2C) |
| Audio | INMP441 (I2S) + SmartElex Speaker (PWM) |
| Buttons | 5x momentary (GPIO 16,17,19,32,4) |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Serial port not found | Check `SERIAL_PORT` in `.env`, run `python run.py --port-scan` |
| Model not loading | Check `ML_MODEL_PATH`, ensure `pip install -e .` in ML folder |
| Voice not working | Verify `NVIDIA_API_KEY` in `.env` |
| Music control not working | Install platform-specific deps (pywin32, playerctl, etc.) |
| Calendar empty | Configure Google/Outlook credentials |

## License

MIT License - See LICENSE file for details.