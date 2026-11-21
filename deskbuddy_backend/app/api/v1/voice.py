"""
Voice Assistant API - Nemotron integration with tool calling.
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, UploadFile, File
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.voice import voice_assistant

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceQuery(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    context: Optional[Dict[str, Any]] = None
    stream: bool = False


class VoiceResponse(BaseModel):
    response_id: str
    text: str
    tool_calls: List[Dict[str, Any]] = []
    audio_url: Optional[str] = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = "en-US-Neural"
    speed: float = 1.0


def get_voice_assistant():
    """Dependency to get voice assistant instance."""
    if voice_assistant is None:
        raise HTTPException(status_code=503, detail="Voice assistant not initialized")
    return voice_assistant


@router.post("/query", response_model=VoiceResponse)
async def voice_query(
    payload: VoiceQuery,
    assistant = Depends(get_voice_assistant)
):
    """Process text query through Nemotron with tool calling."""
    try:
        result = await assistant.process_query(
            text=payload.text,
            context=payload.context
        )
        
        return VoiceResponse(
            response_id=str(uuid.uuid4())[:8],
            text=result.get("text", ""),
            tool_calls=result.get("tool_calls", []),
            audio_url=result.get("audio_url")
        )
    except Exception as e:
        logging.error(f"Voice query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tts")
async def text_to_speech(
    payload: TTSRequest,
    assistant = Depends(get_voice_assistant)
):
    """Convert text to speech."""
    try:
        audio_data = await assistant.synthesize_speech(
            text=payload.text,
            voice=payload.voice,
            speed=payload.speed
        )
        
        # In a real implementation, this would return audio data or a URL
        return {
            "audio_url": "/api/v1/voice/audio/temp_file.wav",
            "duration_estimate": len(payload.text) / 150 * 60  # rough estimate
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stt")
async def speech_to_text(
    audio_file: UploadFile = File(...),
    language: str = "en"
):
    """Speech to text (placeholder - would use Whisper or similar)."""
    # This would integrate with Whisper or similar STT
    return {
        "text": "Transcribed text would appear here",
        "language": language,
        "confidence": 0.95
    }


@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket):
    """WebSocket for real-time voice interaction."""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_bytes()
            
            # Process audio chunk
            # In real implementation: STT -> Query -> TTS -> Audio response
            
            # For now, echo back
            await websocket.send_json({
                "type": "transcript",
                "text": "Received audio chunk",
                "final": False
            })
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"Voice WebSocket error: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})


@router.get("/status")
async def voice_status():
    """Get voice assistant status."""
    return {
        "enabled": True,
        "model": settings.nemotron_model,
        "api_configured": bool(settings.nvidia_api_key),
        "tts_available": True,
        "stt_available": False
    }


@router.get("/tools")
async def list_voice_tools():
    """List available tools for voice assistant."""
    return {
        "tools": [
            {
                "name": "get_device_status",
                "description": "Get current device connection status and sensor readings",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "switch_device_mode",
                "description": "Switch device between inspection and desk buddy mode",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["inspection", "desk_buddy"]}
                    },
                    "required": ["mode"]
                }
            },
            {
                "name": "get_pc_metrics",
                "description": "Get current PC performance metrics (CPU, RAM, GPU, etc.)",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "control_music",
                "description": "Control music playback",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["play", "pause", "next", "previous", "volume"]},
                        "level": {"type": "integer", "minimum": 0, "maximum": 100}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "get_calendar_events",
                "description": "Get upcoming calendar events",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "minimum": 1, "maximum": 30, "default": 7}
                    }
                }
            },
            {
                "name": "run_inspection",
                "description": "Start vibration inspection analysis",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["auto", "cnn", "traditional"], "default": "auto"}
                    }
                }
            },
            {
                "name": "get_inspection_history",
                "description": "Get recent inspection history",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}
                    }
                }
            },
            {
                "name": "set_volume",
                "description": "Set system volume",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "integer", "minimum": 0, "maximum": 100}
                    },
                    "required": ["level"]
                }
            },
            {
                "name": "get_system_info",
                "description": "Get system information",
                "parameters": {"type": "object", "properties": {}}
            }
        ]
    }
