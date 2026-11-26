# Voice Assistant — Omnipect

Push-to-talk voice assistant pipeline: **VOICE button → Wi-Fi HTTP → STT (faster-whisper tiny.en) → Nemotron LLM → TTS (edge-ttS) → 16 kHz PCM WAV → MAX98357A → speaker**.

Transports audio over **Wi-Fi HTTP** (not USB serial). The ESP32 records up to 6 s of 16 kHz mono PCM16, POSTs it to the backend, and plays the spoken reply back through a MAX98357A I²S amp.

> **Note:** Physical playback is gated on wiring the MAX98357A (see Wiring). The firmware and backend voice code are complete and verified end-to-end with a local WAV; the audio path just needs the amp connected.

---

## Pipeline

```
ESP32-S3                       Wi-Fi HTTP                    deskbuddy_backend (PC)
----------                     ----------                    -----------------------
VOICE button (GPIO 17) ───┐                                                       ┌── NVIDIA Nemotron
                          │ POST /api/v1/voice/chat   POST /chat/completions ────┤
Record 6 s @ 16 kHz mono   WAV body                        ← 16 kHz PCM WAV reply  │
PCM16 (≈160 KB)            ─────────────────────────────► TTS edge-ttS / SAPI    │
                          ◄─────────────────────────────   replayed on device     │
Play reply via MAX98357A                                                    │
(BCLK=40, LRC=41, DIN=42)                                               │
```

Stages:
1. **Capture** — VOICE button press starts recording; release (or 6 s max) stops it. Audio is buffered in PSRAM.
2. **STT** — `faster-whisper` (`tiny.en`, CPU) transcribes the WAV. VAD filter keeps only speech segments.
3. **LLM** — Nemotron (`nvidia/nemotron-3-ultra-550b-a55b` via `https://integrate.api.nvidia.com/v1`) reasons over the transcript with tool calling; reasoning is disabled (`chat_template_kwargs: {"enable_thinking": false}`) so it returns direct content in ~1 s.
4. **TTS** — `edge-tts` (`en-US-ChristopherNeural`) synthesizes the reply; decoded to 16 kHz mono PCM16 WAV. Windows SAPI is the offline fallback.
5. **Playback** — Firmware decodes the WAV and streams PCM16 to the MAX98357A via a second `I2SClass`.

---

## Hardware Wiring

| Function | ESP32-S3 GPIO | Notes |
|----------|---------------|-------|
| MAX98357A BCLK | GPIO 40 | I²S bit clock |
| MAX98357A LRC / WS | GPIO 41 | I²S word select |
| MAX98357A DIN / SD | GPIO 42 | I²S data in |
| Speaker (+) | MAX98357A output | 4 Ω, 2 W |
| Speaker (−) | GND | |
| VOICE button | GPIO 17 | Active LOW, INPUT_PULLUP |

**Power:** 5 V 3 A recommended for the 2 W speaker. MAX98357A gain set to 6–9 dB; firmware caps device volume at ~80 % to avoid clipping/distortion.

The MAX98357A is **not yet wired** on the bench. Firmware code for the amp is present (pins 40/41/42) but cannot produce sound until it is connected. Until then, `/voice/chat` still returns WAV; the device just has nothing to play it on.

---

## Backend Setup

### Environment
The voice stack lives in the `inspection` conda environment:

```powershell
# From the repo root
cd deskbuddy_backend
C:\Users\Suryansh3584\.conda\envs\inspection\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Bind `0.0.0.0` so the ESP32 on the LAN can reach port 8080. Startup takes ~20 s (Whisper model loads lazily on first request; the ~75 MB `tiny.en` model downloads once from Hugging Face and is cached at `%USERPROFILE%\.cache\huggingface\hub\models--Systran--faster-whisper-tiny.en`).

### `.env` (voice-relevant keys)

```ini
NVIDIA_API_KEY=your_nvidia_api_key_here
NEMOTRON_MODEL=nvidia/nemotron-3-ultra-550b-a55b
NEMOTRON_BASE_URL=https://integrate.api.nvidia.com/v1

ENABLE_VOICE_ASSISTANT=true
WHISPER_MODEL=tiny.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
TTS_VOICE=en-US-ChristopherNeural
```

### Known BLAS fix (conda env)
The conda-pinned `numpy`/`scipy` link against an MKL 2026.1.0 shim that crashes on the first float32 matmul (`0xC06D007F` in KERNELBASE) — this is what killed the first E2E run. Fix (applied to the `inspection` env):

```powershell
C:\Users\Suryansh3584\.conda\envs\inspection\python.exe -m pip install --force-reinstall --no-deps "numpy==2.1.3" "scipy==1.14.1"
```

These PyPI wheels ship self-contained OpenBLAS and do not conflict with MKL/CT2. Verified: `faster-whisper` transcribes `test_question.wav` in ~0.7 s both `float32` and `int8`.

---

## Firmware (ESP32-S3)

The voice client is in `DeskBuddy_Companion.ino`. Compile command:

```powershell
& "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" compile --fqbn "esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default" firmware/arduino/DeskBuddy_Companion
```

### Voice config
Copy `firmware/arduino/DeskBuddy_Companion/voice_config.example.h` to `voice_config.h` (gitignored) and fill in your Wi-Fi credentials and the PC's LAN IP:

```cpp
// voice_config.h  (not committed)
#ifndef VOICE_CONFIG_H
#define VOICE_CONFIG_H
#define VOICE_WIFI_SSID "YourSSID"
#define VOICE_WIFI_PASS "YourPassword"
#define VOICE_SERVER_URL "http://192.168.x.x:8080"   // PC LAN IP, not 127.0.0.1
#define VOICE_WIFI_ALWAYS_ON 0                        // 1 = keep Wi-Fi up; 0 = 120 s idle disconnect
#endif
```

Wi-Fi can also be configured at runtime over serial (`{"cmd":"wifi",...}` / `{"cmd":"voice_server",...}`) and persisted in NVS, so `voice_config.h` is optional.

### Operation
- Press **VOICE (GPIO 17)** → `voiceToggle()` starts/stops capture.
- Max capture: 6 s. The device shows an OLED overlay with a progress bar and the wrapped transcript/reply.
- On reply, the firmware decodes the WAV and plays it via `audioOut.playWAV()` through the MAX98357A.
- Serial commands: `{"cmd":"voice",...}`, `{"cmd":"wifi",...}`, `{"cmd":"voice_server",...}`, `{"cmd":"voice_config",...}` handled by `handleBackendLine`.

**Currently blocked:** physical playback until the MAX98357A is wired. Device Wi-Fi test is also blocked pending SSID/password + PC LAN IP and a Windows Firewall rule allowing the ESP32 to reach port 8080.

---

## API Reference

Base: `http://<pc-lan-ip>:8080/api/v1/voice`

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/health` | GET | — | Service probe: model, STT/TTS config |
| `/status` | GET | — | Voice enabled, API configured, sample rate |
| `/chat` | POST | raw WAV bytes (`Content-Type: audio/wav`) or multipart `audio` file | Full STT → Nemotron → TTS; returns 16 kHz PCM WAV body + `X-Transcript` / `X-Reply-Text` headers |
| `/chat/json` | POST | raw WAV | JSON variant for dashboards/tests |
| `/tts` | POST | JSON `{text, voice?, speed?}` | Synthesize text → 16 kHz PCM WAV |
| `/stt` | POST | `UploadFile` audio | Transcribe WAV/MP3 → text |
| `/reset` | POST | `session_id` | Clear conversation history |
| `/ws` | WebSocket | binary WAV in | Real-time voice: transcript/reply JSON + WAV bytes out |
| `/tools` | GET | — | List available Nemotron tools |

The `/chat` response headers include URL-encoded `X-Transcript` and `X-Reply-Text` so the device can display them without parsing the audio.

---

## Verified Behavior

End-to-end test with `deskbuddy_backend/test_question.wav` (2.4 s, "What is the health of motor one?"):

```
status: 200
elapsed: 15.3 s
transcript: What is the health of motor one?
reply: Motor one is in excellent condition with a health index of 94.8%. ...
content-type: audio/wav
audio bytes: 544,556   (WAV, PCM_16, 16000 Hz, mono, 17.0 s)
stt error: None
tts error: None
```

Unit tests: `tests/test_voice_audio.py` + `tests/test_voice_api.py` — **51 tests pass, exit 0**.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Backend exits with `0xC06D007F` on first Whisper request | Conda MKL BLAS crash. Reinstall `numpy`/`scipy` from PyPI (see Backend Setup). |
| `ConnectionError` / server disconnect from ESP32 | Backend not running on `0.0.0.0:8080`, or Windows Firewall blocks port 8080. Use the PC's LAN IP, not `127.0.0.1`. |
| No audio from device | MAX98357A not wired yet (pins 40/41/42). Wire the amp, 5 V 3 A power, and the 4 Ω 2 W speaker. |
| Transcript empty | Whisper model failed to load/download; check `%USERPROFILE%\.cache\huggingface\hub\models--Systran--faster-whisper-tiny.en` and network access. |
| `413 Audio body too large` | Capture exceeds `voice_max_upload_bytes` (10 MB). Keep captures ≤ 6 s. |
| Reply sounds robotic/wrong speed | TTS voice/speed from `.env` (`TTS_VOICE`, `TTS_SPEED`); SAPI fallback sounds different from edge-tts. |
| Wi-Fi never connects | Check SSID/password in `voice_config.h` or serial `wifi` command; confirm the PC and ESP32 are on the same LAN. |

---

## Next Steps (optional)

- Wire MAX98357A (40/41/42) + 4 Ω 2 W speaker + 5 V 3 A supply; test push-to-talk end-to-end.
- Add `VOICE_ASSISTANT.md` (this file) + update `README.md` (done).
- Perimeter progress ring on the music page, RenderDiag Stage F long-title marquee, INA219 `/api/v1/power` telemetry.
