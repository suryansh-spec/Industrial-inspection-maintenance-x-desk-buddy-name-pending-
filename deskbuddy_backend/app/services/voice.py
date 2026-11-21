"""Voice Assistant Service - NVIDIA Nemotron integration with Function Calling and TTS.

Orchestrates:
1. Speech-to-Text transcription.
2. Multi-turn Nemotron reasoning with OpenAI-compatible tool calling.
3. Tool dispatching to industrial diagnostics, music, and desk buddy services.
4. Neural text-to-speech synthesis via edge-tts with local SAPI fallback.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
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

    async def initialize(self) -> None:
        """Prepare the HTTP client and validate configuration."""
        if self.initialized:
            return

        self.api_key = settings.nvidia_api_key
        self.model = settings.nemotron_model or "nvidia/nemotron-4-340b-instruct"
        self.base_url = settings.nemotron_base_url or "https://integrate.api.nvidia.com/v1"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self.initialized = True

        if self.api_key:
            logger.info("Nemotron Voice Assistant initialized (model=%s)", self.model)
        else:
            logger.warning("Nemotron Voice Assistant running without NVIDIA_API_KEY (mock/fallback mode)")

    async def cleanup(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self.initialized = False

    async def process_query(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a text query with Nemotron, executing any requested tool calls."""
        if not self.initialized:
            await self.initialize()

        system_prompt = (
            "You are DeskBuddy, an intelligent desk companion and industrial machine inspector. "
            "You have tools to examine motor health, predict Remaining Useful Life (RUL), "
            "control music and lyrics, and display expressions. "
            "When asked to check machines, play music, or change expressions, call the appropriate tool. "
            "Keep answers concise, direct, helpful, and natural for speech."
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "system", "content": f"Live telemetry context: {json.dumps(context)}"})
        messages.append({"role": "user", "content": text})

        executed_tools: List[Dict[str, Any]] = []

        # Fallback if no API key is configured
        if not self.api_key or self._client is None:
            logger.info("No NVIDIA_API_KEY set; running heuristic tool matcher.")
            lower = text.lower()
            if "inspect" in lower or "motor" in lower or "vibration" in lower:
                tool_res = await dispatch_tool_call("run_motor_inspection", {"motor_id": "motor_1"})
                executed_tools.append({"name": "run_motor_inspection", "result": tool_res})
                return {
                    "text": (
                        f"Inspection completed on motor 1. Condition: {tool_res.get('predicted_condition', 'Normal')} "
                        f"with {round(tool_res.get('confidence', 0.99) * 100, 1)}% confidence. Vibration RMS is {tool_res.get('vibration_rms_g', 0.02)}g."
                    ),
                    "tool_calls": executed_tools,
                }
            elif "rul" in lower or "stop working" in lower or "age" in lower or "break" in lower or "timeline" in lower:
                tool_res = await dispatch_tool_call("get_equipment_rul", {"motor_id": "motor_1"})
                executed_tools.append({"name": "get_equipment_rul", "result": tool_res})
                return {
                    "text": (
                        f"Motor 1 is currently {tool_res.get('calendar_age', '7 months old')} with {tool_res.get('operating_age_hours', 1840)} operating hours. "
                        f"Predicted failure is in approximately {tool_res.get('predicted_rul_days', 164)} days ({tool_res.get('projected_failure_date', 'May 2027')})."
                    ),
                    "tool_calls": executed_tools,
                }
            elif "play" in lower:
                tool_res = await dispatch_tool_call("control_media", {"action": "play"})
                executed_tools.append({"name": "control_media", "result": tool_res})
                return {"text": "Resuming music playback.", "tool_calls": executed_tools}
            elif "pause" in lower or "stop music" in lower:
                tool_res = await dispatch_tool_call("control_media", {"action": "pause"})
                executed_tools.append({"name": "control_media", "result": tool_res})
                return {"text": "Music paused.", "tool_calls": executed_tools}
            elif "happy" in lower or "smile" in lower:
                await dispatch_tool_call("set_buddy_expression", {"expression": "happy"})
                return {"text": "I set my expression to happy!", "tool_calls": [{"name": "set_buddy_expression"}]}

            return {
                "text": f"I heard: '{text}'. Set your NVIDIA_API_KEY in .env to unlock full Nemotron reasoning and tool calling.",
                "tool_calls": [],
            }

        # Multi-turn Nemotron API loop with function calling
        try:
            req_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 512,
                "tools": NEMOTRON_TOOLS_SCHEMA,
                "tool_choice": "auto",
            }

            resp = await self._client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=req_payload,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            # Check if model requested tool calls
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                return {
                    "text": msg.get("content", ""),
                    "tool_calls": [],
                }

            # Execute tool calls
            messages.append(msg)
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    args = {}

                result = await dispatch_tool_call(name, args)
                executed_tools.append({"name": name, "args": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{name}"),
                    "name": name,
                    "content": json.dumps(result),
                })

            # Follow-up request to synthesize natural voice answer
            followup_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 256,
            }
            followup_resp = await self._client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=followup_payload,
            )
            followup_resp.raise_for_status()
            final_data = followup_resp.json()
            final_answer = final_data["choices"][0]["message"].get("content", "")

            return {
                "text": final_answer,
                "tool_calls": executed_tools,
            }

        except Exception as exc:
            logger.error("Nemotron voice query error: %s", exc)
            return {"text": f"Nemotron query error: {exc}", "tool_calls": []}

    async def synthesize_speech(
        self,
        text: str,
        voice: str = "en-US-ChristopherNeural",
        speed: float = 1.0,
    ) -> Optional[bytes]:
        """Convert text to speech audio bytes using edge-tts (neural) with SAPI fallback."""
        if not text.strip():
            return None

        # 1. Try edge-tts for high-quality neural voice
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
            logger.debug("edge-tts synthesis failed, trying local SAPI: %s", exc)

        # 2. Local Windows SAPI fallback
        try:
            import win32com.client

            voice_engine = win32com.client.Dispatch("SAPI.SpVoice")
            asyncio.get_event_loop().run_in_executor(None, voice_engine.Speak, text)
            return None
        except Exception as exc:
            logger.debug("Local SAPI speech failed: %s", exc)

        return None


voice_assistant = VoiceAssistant()
