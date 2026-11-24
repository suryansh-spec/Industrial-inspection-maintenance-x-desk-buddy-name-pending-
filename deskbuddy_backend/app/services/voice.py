"""Voice Assistant Service - NVIDIA Nemotron integration with Function Calling and TTS.

Orchestrates:
1. Speech-to-text transcription with faster-whisper (local, tiny.en by default).
2. Multi-turn Nemotron reasoning with OpenAI-compatible tool calling.
3. Tool dispatching to industrial diagnostics, music, and desk buddy services.
4. Neural text-to-speech synthesis via edge-tts, returned as 16 kHz PCM WAV,
   with a Windows SAPI fallback when the network is unavailable.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services import voice_audio
from app.services.voice_tools import NEMOTRON_TOOLS_SCHEMA, dispatch_tool_call

logger = logging.getLogger(__name__)


class VoiceAssistant:
    """Async voice orchestrator using NVIDIA Nemotron and local tool dispatch."""

    def __init__(self):
        self.initialized = False
        self.api_key: Optional[str] = None
        self.model: str = settings.nemotron_model
        self.base_url: str = settings.nemotron_base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._whisper = None
        self._whisper_lock = asyncio.Lock()
        self._history: Dict[str, List[Dict[str, Any]]] = {}

    async def initialize(self) -> None:
        """Prepare the HTTP client and validate configuration."""
        if self.initialized:
            return

        self.api_key = settings.nvidia_api_key
        self.model = settings.nemotron_model or "nvidia/nemotron-4-340b-instruct"
        self.base_url = settings.nemotron_base_url or "https://integrate.api.nvidia.com/v1"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(settings.voice_timeout))
        self.initialized = True

        if self.api_key:
            logger.info("Nemotron Voice Assistant initialized (model=%s)", self.model)
        else:
            logger.warning("Nemotron Voice Assistant running without NVIDIA_API_KEY (mock/fallback mode)")

    async def cleanup(self) -> None:
        """Close the HTTP client and release the Whisper model."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._whisper = None
        self.initialized = False

    # ------------------------------------------------------------------
    # Speech-to-text
    # ------------------------------------------------------------------
    async def _ensure_whisper(self):
        if self._whisper is not None:
            return self._whisper

        async with self._whisper_lock:
            if self._whisper is None:
                from faster_whisper import WhisperModel

                logger.info(
                    "Loading Whisper model '%s' (device=%s, compute_type=%s); "
                    "the first run downloads it from Hugging Face.",
                    settings.whisper_model,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                )
                self._whisper = await asyncio.to_thread(
                    WhisperModel,
                    settings.whisper_model,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                )
                logger.info("Whisper model ready: %s", settings.whisper_model)
        return self._whisper

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transcribe WAV/MP3 bytes to text with faster-whisper."""
        language = language or settings.whisper_language or None
        if not audio_bytes:
            return {"text": "", "language": language or "", "duration": 0.0}

        try:
            pcm, _ = await asyncio.to_thread(
                voice_audio.decode_audio_to_pcm16, audio_bytes, 16000
            )
        except Exception as exc:
            logger.warning("Audio decode failed: %s", exc)
            return {"text": "", "language": language or "", "duration": 0.0, "error": str(exc)}

        if pcm.size == 0:
            return {"text": "", "language": language or "", "duration": 0.0}

        audio = pcm.astype("float32") / 32768.0

        try:
            model = await self._ensure_whisper()

            def _run():
                segments, info = model.transcribe(
                    audio,
                    language=language or None,
                    beam_size=max(1, int(settings.whisper_beam_size)),
                    vad_filter=bool(settings.whisper_vad_filter),
                    condition_on_previous_text=False,
                )
                text = " ".join((segment.text or "").strip() for segment in segments).strip()
                return text, info

            text, info = await asyncio.to_thread(_run)
        except Exception as exc:
            logger.exception("Whisper transcription failed")
            return {
                "text": "",
                "language": language or "",
                "duration": round(len(pcm) / 16000.0, 2),
                "error": str(exc),
            }

        return {
            "text": text,
            "language": getattr(info, "language", language or ""),
            "language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
            "duration": round(float(getattr(info, "duration", len(pcm) / 16000.0) or 0.0), 2),
        }

    # ------------------------------------------------------------------
    # Text-to-speech
    # ------------------------------------------------------------------
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "en-US-ChristopherNeural",
        speed: float = 1.0,
    ) -> Optional[bytes]:
        """Convert text to MP3 audio bytes using edge-tts (kept for compatibility)."""
        if not text.strip():
            return None

        try:
            import edge_tts

            rate_str = f"{int((speed - 1.0) * 100):+d}%"
            communicate = edge_tts.Communicate(text, voice, rate=rate_str)
            audio_buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buf.extend(chunk["data"])
            if audio_buf:
                return bytes(audio_buf)
        except Exception as exc:
            logger.debug("edge-tts synthesis failed: %s", exc)

        return None

    async def synthesize_speech_wav(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        """Synthesize speech and return 16 kHz mono PCM WAV bytes."""
        pcm, sample_rate = await voice_audio.tts_to_pcm16(
            text,
            voice or settings.tts_voice,
            speed if speed is not None else settings.tts_speed,
        )
        return voice_audio.pcm16_to_wav(pcm, sample_rate)

    # ------------------------------------------------------------------
    # Nemotron reasoning
    # ------------------------------------------------------------------
    def _chat_extras(self) -> Dict[str, Any]:
        if settings.voice_disable_thinking:
            # Nemotron 3 reasoning models otherwise spend the token budget on
            # reasoning_content and can return content=null.
            return {"chat_template_kwargs": {"enable_thinking": False}}
        return {}

    async def _post_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST to the OpenAI-compatible endpoint, retrying without extras on 400/422."""
        if self._client is None:
            raise RuntimeError("Voice assistant HTTP client is not initialized")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = await self._client.post(url, headers=headers, json=payload)

        if response.status_code in (400, 422) and "chat_template_kwargs" in payload:
            logger.warning(
                "Nemotron rejected chat_template_kwargs (%s); retrying without it",
                response.status_code,
            )
            fallback = dict(payload)
            fallback.pop("chat_template_kwargs", None)
            response = await self._client.post(url, headers=headers, json=fallback)

        response.raise_for_status()
        return response.json()

    def _remember(self, session_id: str, user_text: str, answer: str) -> None:
        if settings.voice_history_turns <= 0 or not answer:
            return
        history = self._history.setdefault(session_id, [])
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer})
        max_messages = settings.voice_history_turns * 2
        if len(history) > max_messages:
            del history[:-max_messages]

    async def reset_session(self, session_id: str = "default") -> None:
        """Forget the conversation history for a device/session."""
        self._history.pop(session_id, None)

    async def process_query(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Process a text query with Nemotron, executing any requested tool calls."""
        if not self.initialized:
            await self.initialize()

        system_prompt = (
            "You are DeskBuddy, an intelligent desk companion and industrial machine inspector. "
            "You have tools to examine motor health, predict Remaining Useful Life (RUL), "
            "control music and lyrics, and display expressions. "
            "When asked to check machines, play music, or change expressions, call the appropriate tool. "
            "Keep answers concise, direct, helpful, and natural for speech. "
            "Never mention tool names, JSON, or internal implementation details."
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "system", "content": f"Live telemetry context: {json.dumps(context)}"})

        history = self._history.get(session_id, [])
        if history and settings.voice_history_turns > 0:
            messages.extend(history[-(settings.voice_history_turns * 2):])
        messages.append({"role": "user", "content": text})

        executed_tools: List[Dict[str, Any]] = []

        # Fallback if no API key is configured.
        if not self.api_key or self._client is None:
            logger.info("No NVIDIA_API_KEY set; running heuristic tool matcher.")
            lower = text.lower()
            if "inspect" in lower or "motor" in lower or "vibration" in lower:
                tool_res = await dispatch_tool_call("run_motor_inspection", {"motor_id": "motor_1"})
                executed_tools.append({"name": "run_motor_inspection", "result": tool_res})
                answer = (
                    f"Inspection completed on motor 1. Condition: {tool_res.get('predicted_condition', 'Normal')} "
                    f"with {round(tool_res.get('confidence', 0.99) * 100, 1)}% confidence. "
                    f"Vibration RMS is {tool_res.get('vibration_rms_g', 0.02)}g."
                )
                self._remember(session_id, text, answer)
                return {"text": answer, "tool_calls": executed_tools}
            if "rul" in lower or "stop working" in lower or "age" in lower or "break" in lower or "timeline" in lower:
                tool_res = await dispatch_tool_call("get_equipment_rul", {"motor_id": "motor_1"})
                executed_tools.append({"name": "get_equipment_rul", "result": tool_res})
                answer = (
                    f"Motor 1 is currently {tool_res.get('calendar_age', '7 months old')} with "
                    f"{tool_res.get('operating_age_hours', 1840)} operating hours. "
                    f"Predicted failure is in approximately {tool_res.get('predicted_rul_days', 164)} days "
                    f"({tool_res.get('projected_failure_date', 'May 2027')})."
                )
                self._remember(session_id, text, answer)
                return {"text": answer, "tool_calls": executed_tools}
            if "pause" in lower or "stop music" in lower:
                tool_res = await dispatch_tool_call("control_media", {"action": "pause"})
                executed_tools.append({"name": "control_media", "result": tool_res})
                answer = "Music paused."
                self._remember(session_id, text, answer)
                return {"text": answer, "tool_calls": executed_tools}
            if "play" in lower:
                tool_res = await dispatch_tool_call("control_media", {"action": "play"})
                executed_tools.append({"name": "control_media", "result": tool_res})
                answer = "Resuming music playback."
                self._remember(session_id, text, answer)
                return {"text": answer, "tool_calls": executed_tools}
            if "happy" in lower or "smile" in lower:
                await dispatch_tool_call("set_buddy_expression", {"expression": "happy"})
                answer = "I set my expression to happy!"
                self._remember(session_id, text, answer)
                return {"text": answer, "tool_calls": [{"name": "set_buddy_expression"}]}

            answer = (
                f"I heard: '{text}'. Set your NVIDIA_API_KEY in .env to unlock full "
                "Nemotron reasoning and tool calling."
            )
            self._remember(session_id, text, answer)
            return {"text": answer, "tool_calls": []}

        # Multi-turn Nemotron API loop with function calling.
        try:
            req_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max(64, int(settings.voice_max_tokens)),
                "tools": NEMOTRON_TOOLS_SCHEMA,
                "tool_choice": "auto",
                **self._chat_extras(),
            }
            data = await self._post_chat(req_payload)
            choice = data["choices"][0]
            msg = choice["message"]

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                answer = (msg.get("content") or "").strip()
                if not answer:
                    answer = "Sorry, I couldn't generate a response. Please try again."
                self._remember(session_id, text, answer)
                return {"text": answer, "tool_calls": []}

            # Execute tool calls and send their results back to Nemotron.
            assistant_message: Dict[str, Any] = {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {}

                result = await dispatch_tool_call(name, args)
                executed_tools.append({"name": name, "args": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{name}"),
                        "name": name,
                        "content": json.dumps(result),
                    }
                )

            followup_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max(64, int(settings.voice_max_tokens)),
                **self._chat_extras(),
            }
            final_data = await self._post_chat(followup_payload)
            answer = (final_data["choices"][0]["message"].get("content") or "").strip()
            if not answer:
                answer = "I completed the request, but I couldn't produce a spoken summary."
            self._remember(session_id, text, answer)

            return {"text": answer, "tool_calls": executed_tools}

        except Exception as exc:
            logger.error("Nemotron voice query error: %s", exc)
            return {"text": f"Nemotron query error: {exc}", "tool_calls": executed_tools}

    # ------------------------------------------------------------------
    # End-to-end audio
    # ------------------------------------------------------------------
    async def process_audio(
        self,
        audio_bytes: bytes,
        session_id: str = "default",
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transcribe, reason, and synthesize a spoken reply.

        Returns a dict with ``transcript``, ``text``, ``tool_calls``, ``wav``
        (16 kHz PCM WAV bytes; empty if TTS failed), and optional error keys.
        """
        transcription = await self.transcribe(audio_bytes, language)
        transcript = (transcription.get("text") or "").strip()

        if not transcript:
            reply = "Sorry, I didn't catch that. Please try again."
            try:
                wav = await self.synthesize_speech_wav(reply)
            except Exception as exc:
                logger.error("TTS failed for fallback reply: %s", exc)
                wav = b""
            return {
                "transcript": "",
                "text": reply,
                "tool_calls": [],
                "wav": wav,
                "language": transcription.get("language", ""),
                "stt_error": transcription.get("error"),
            }

        result = await self.process_query(transcript, session_id=session_id)
        reply = (result.get("text") or "").strip() or "Sorry, I couldn't generate a response."

        wav = b""
        tts_error = None
        try:
            wav = await self.synthesize_speech_wav(reply)
        except Exception as exc:
            logger.error("TTS synthesis failed: %s", exc)
            tts_error = str(exc)

        return {
            "transcript": transcript,
            "text": reply,
            "tool_calls": result.get("tool_calls", []),
            "wav": wav,
            "language": transcription.get("language", ""),
            "tts_error": tts_error,
        }


voice_assistant = VoiceAssistant()
