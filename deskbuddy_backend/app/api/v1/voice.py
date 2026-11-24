"""
Voice Assistant API - Nemotron integration with tool calling.

Two transports are supported:

* ``POST /voice/chat`` - the ESP32 uploads a 16 kHz PCM WAV body (raw
  ``audio/wav`` or multipart) and receives a 16 kHz PCM WAV reply.  The
  transcript and spoken reply are also returned in the ``X-Transcript`` and
  ``X-Reply-Text`` headers (URL-encoded) so the device can display them.
* ``POST /voice/query`` + ``POST /voice/tts`` - text-only dashboard flow.
"""
import base64
import logging
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.voice import voice_assistant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceQuery(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    context: Optional[Dict[str, Any]] = None
    stream: bool = False
    session_id: str = "default"


class VoiceResponse(BaseModel):
    response_id: str
    text: str
    tool_calls: List[Dict[str, Any]] = []
    audio_url: Optional[str] = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Optional[str] = None
    speed: float = 1.0


def get_voice_assistant():
    """Dependency to get the voice assistant instance."""
    if voice_assistant is None:
        raise HTTPException(status_code=503, detail="Voice assistant not initialized")
    return voice_assistant


def _resolve_voice(voice: Optional[str]) -> str:
    if not voice or voice in ("en-US-Neural", "default"):
        return settings.tts_voice
    return voice


async def _read_audio_request(request: Request) -> bytes:
    """Read raw or multipart audio from a request without requiring a form."""
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("audio") or form.get("file")
        if upload is None:
            raise HTTPException(status_code=400, detail="Missing 'audio' file")
        if hasattr(upload, "read"):
            return await upload.read()
        return bytes(upload)
    return await request.body()


@router.post("/chat")
async def voice_chat(
    request: Request,
    session_id: str = "deskbuddy",
    language: str = "en",
    assistant=Depends(get_voice_assistant),
):
    """Full STT -> Nemotron -> TTS turn, returning a 16 kHz PCM WAV body."""
    audio_bytes = await _read_audio_request(request)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio body")
    if len(audio_bytes) > settings.voice_max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio body too large")

    result = await assistant.process_audio(
        audio_bytes,
        session_id=session_id,
        language=language,
    )
    transcript = result.get("transcript", "") or ""
    reply = result.get("text", "") or ""
    wav = result.get("wav") or b""

    headers = {
        "X-Transcript": quote(transcript, safe=""),
        "X-Reply-Text": quote(reply, safe=""),
        "X-Session-Id": session_id,
        "X-Audio-Format": "pcm16-wav",
        "X-Audio-Sample-Rate": "16000",
    }
    if result.get("stt_error"):
        headers["X-STT-Error"] = "1"
    if result.get("tts_error") or not wav:
        headers["X-TTS-Error"] = "1"

    return Response(content=wav, media_type="audio/wav", headers=headers)


@router.post("/chat/json")
async def voice_chat_json(
    request: Request,
    session_id: str = "deskbuddy",
    language: str = "en",
    assistant=Depends(get_voice_assistant),
):
    """JSON variant for dashboards and automated tests."""
    audio_bytes = await _read_audio_request(request)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio body")
    if len(audio_bytes) > settings.voice_max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio body too large")

    result = await assistant.process_audio(
        audio_bytes,
        session_id=session_id,
        language=language,
    )
    wav = result.get("wav") or b""
    return {
        "transcript": result.get("transcript", ""),
        "text": result.get("text", ""),
        "tool_calls": result.get("tool_calls", []),
        "language": result.get("language", ""),
        "audio_base64": base64.b64encode(wav).decode("ascii") if wav else "",
        "audio_format": "pcm16-wav",
        "audio_sample_rate": 16000,
        "stt_error": result.get("stt_error"),
        "tts_error": result.get("tts_error"),
    }


@router.post("/query", response_model=VoiceResponse)
async def voice_query(
    payload: VoiceQuery,
    assistant=Depends(get_voice_assistant),
):
    """Process a text query through Nemotron with tool calling."""
    try:
        result = await assistant.process_query(
            text=payload.text,
            context=payload.context,
            session_id=payload.session_id,
        )
        return VoiceResponse(
            response_id=str(uuid.uuid4())[:8],
            text=result.get("text", ""),
            tool_calls=result.get("tool_calls", []),
            audio_url=None,
        )
    except Exception as exc:
        logger.exception("Voice query error")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/tts")
async def text_to_speech(
    payload: TTSRequest,
    assistant=Depends(get_voice_assistant),
):
    """Convert text to a 16 kHz PCM WAV file."""
    try:
        wav = await assistant.synthesize_speech_wav(
            text=payload.text,
            voice=_resolve_voice(payload.voice),
            speed=payload.speed,
        )
        return Response(
            content=wav,
            media_type="audio/wav",
            headers={"Content-Disposition": 'inline; filename="tts.wav"'},
        )
    except Exception as exc:
        logger.exception("TTS error")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stt")
async def speech_to_text(
    audio_file: UploadFile = File(...),
    language: str = "en",
    assistant=Depends(get_voice_assistant),
):
    """Transcribe an uploaded WAV/MP3 file with faster-whisper."""
    data = await audio_file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(data) > settings.voice_max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio file too large")
    return await assistant.transcribe(data, language)


@router.post("/reset")
async def reset_voice_session(
    session_id: str = "deskbuddy",
    assistant=Depends(get_voice_assistant),
):
    """Clear the conversation history for a session."""
    await assistant.reset_session(session_id)
    return {"status": "reset", "session_id": session_id}


@router.get("/health")
async def voice_health():
    """Lightweight connectivity probe for the ESP32."""
    return {
        "ok": True,
        "model": settings.nemotron_model,
        "stt_model": settings.whisper_model,
        "tts_voice": settings.tts_voice,
        "audio_sample_rate": 16000,
    }


@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket):
    """WebSocket for real-time voice interaction (binary WAV in, WAV out)."""
    await websocket.accept()
    session_id = "ws"

    try:
        while True:
            data = await websocket.receive_bytes()
            result = await voice_assistant.process_audio(data, session_id=session_id)
            await websocket.send_json(
                {
                    "type": "transcript",
                    "text": result.get("transcript", ""),
                    "final": True,
                }
            )
            await websocket.send_json({"type": "reply", "text": result.get("text", "")})
            wav = result.get("wav") or b""
            if wav:
                await websocket.send_bytes(wav)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Voice WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@router.get("/status")
async def voice_status():
    """Get voice assistant status."""
    return {
        "enabled": bool(settings.enable_voice_assistant),
        "model": settings.nemotron_model,
        "api_configured": bool(settings.nvidia_api_key),
        "tts_available": True,
        "tts_voice": settings.tts_voice,
        "stt_available": True,
        "stt_model": settings.whisper_model,
        "audio_sample_rate": 16000,
    }


@router.get("/tools")
async def list_voice_tools():
    """List available tools for voice assistant."""
    return {
        "tools": [
            {
                "name": "run_motor_inspection",
                "description": "Trigger live vibration sampling and fault classification",
                "parameters": {"type": "object", "properties": {"motor_id": {"type": "string"}}},
            },
            {
                "name": "get_motor_health",
                "description": "Get current health score and latest diagnosis",
                "parameters": {"type": "object", "properties": {"motor_id": {"type": "string"}}},
            },
            {
                "name": "get_equipment_rul",
                "description": "Predict remaining useful life and failure timeline",
                "parameters": {"type": "object", "properties": {"motor_id": {"type": "string"}}},
            },
            {
                "name": "control_media",
                "description": "Control music playback",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["play", "pause", "next", "previous", "volume_up", "volume_down"],
                        },
                        "level": {"type": "integer", "minimum": 0, "maximum": 100},
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "get_now_playing",
                "description": "Get details on the currently playing track",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "set_buddy_expression",
                "description": "Set the OLED eye expression",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
            {
                "name": "get_system_telemetry",
                "description": "Get PC hardware metrics",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {"type": "string", "enum": ["all", "cpu", "gpu", "temps", "memory"]}
                    },
                },
            },
            {
                "name": "set_desk_mode",
                "description": "Switch between desk buddy and inspection modes",
                "parameters": {
                    "type": "object",
                    "properties": {"mode": {"type": "string", "enum": ["desk_buddy", "inspection"]}},
                    "required": ["mode"],
                },
            },
            {
                "name": "start_pomodoro",
                "description": "Start a Pomodoro focus timer",
                "parameters": {"type": "object", "properties": {"minutes": {"type": "integer"}}},
            },
        ]
    }
