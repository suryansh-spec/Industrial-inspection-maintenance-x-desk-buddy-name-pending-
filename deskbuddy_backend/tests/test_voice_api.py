"""Tests for the voice HTTP endpoints (services monkeypatched; no network)."""
import base64

from app.services.voice import voice_assistant


def _fake_audio_result(audio_bytes: bytes, session_id: str = "deskbuddy", language: str = "en"):
    return {
        "transcript": "hello world",
        "text": "hi there",
        "tool_calls": [],
        "wav": b"RIFFfake-wav",
        "language": "en",
        "stt_error": None,
        "tts_error": None,
    }


def test_chat_returns_wav_and_headers(test_client, monkeypatch):
    async def fake_process_audio(audio_bytes, session_id="deskbuddy", language="en"):
        assert audio_bytes[:4] == b"RIFF"
        return _fake_audio_result(audio_bytes, session_id, language)

    monkeypatch.setattr(voice_assistant, "process_audio", fake_process_audio)

    response = test_client.post(
        "/api/v1/voice/chat",
        content=b"RIFF....WAVEfmt ",
        headers={"Content-Type": "audio/wav", "X-Session-Id": "test"},
    )

    assert response.status_code == 200
    assert response.content == b"RIFFfake-wav"
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-transcript"] == "hello%20world"
    assert response.headers["x-reply-text"] == "hi%20there"
    assert response.headers["x-audio-format"] == "pcm16-wav"


def test_chat_json_returns_base64_audio(test_client, monkeypatch):
    async def fake_process_audio(audio_bytes, session_id="deskbuddy", language="en"):
        return _fake_audio_result(audio_bytes, session_id, language)

    monkeypatch.setattr(voice_assistant, "process_audio", fake_process_audio)

    response = test_client.post(
        "/api/v1/voice/chat/json",
        content=b"RIFF....WAVEfmt ",
        headers={"Content-Type": "audio/wav"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "hello world"
    assert data["text"] == "hi there"
    assert base64.b64decode(data["audio_base64"]) == b"RIFFfake-wav"


def test_chat_rejects_empty_body(test_client):
    response = test_client.post(
        "/api/v1/voice/chat",
        content=b"",
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 400


def test_stt_uses_whisper(test_client, monkeypatch):
    async def fake_transcribe(audio_bytes, language=None):
        assert audio_bytes
        return {"text": "transcribed", "language": language or "en", "duration": 1.0}

    monkeypatch.setattr(voice_assistant, "transcribe", fake_transcribe)

    response = test_client.post(
        "/api/v1/voice/stt",
        files={"audio_file": ("sample.wav", b"RIFF....WAVE", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "transcribed"


def test_tts_returns_wav(test_client, monkeypatch):
    async def fake_wav(text, voice=None, speed=None):
        assert text == "hello"
        return b"RIFFtts-wav"

    monkeypatch.setattr(voice_assistant, "synthesize_speech_wav", fake_wav)

    response = test_client.post("/api/v1/voice/tts", json={"text": "hello"})

    assert response.status_code == 200
    assert response.content == b"RIFFtts-wav"
    assert response.headers["content-type"] == "audio/wav"


def test_reset_and_health(test_client, monkeypatch):
    async def fake_reset(session_id="default"):
        return None

    monkeypatch.setattr(voice_assistant, "reset_session", fake_reset)

    reset = test_client.post("/api/v1/voice/reset", params={"session_id": "test"})
    assert reset.status_code == 200
    assert reset.json()["status"] == "reset"

    health = test_client.get("/api/v1/voice/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
