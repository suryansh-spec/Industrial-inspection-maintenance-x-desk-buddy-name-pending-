"""
Voice Assistant Service - Nemotron integration with tool calling.
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Callable

from openai import AsyncOpenAI
from desktop_bridge.config import settings

logger = logging.getLogger(__name__)


class VoiceAssistant:
    """Voice assistant using Nemotron with tool calling."""
    
    def __init__(self):
        self.client = None
        self.tools = self._get_tools()
        self._tool_functions: Dict[str, Callable] = {}
        self._register_tools()
    
    def _get_tools(self) -> List[Dict]:
        """Return tool definitions for Nemotron."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_device_status",
                    "description": "Get current device connection status and sensor readings",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "switch_device_mode",
                    "description": "Switch device between inspection and desk buddy mode",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["inspection", "desk_buddy"]}
                        },
                        "required": ["mode"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pc_metrics",
                    "description": "Get current PC performance metrics (CPU, RAM, GPU, etc.)",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
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
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_calendar_events",
                    "description": "Get upcoming calendar events",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "minimum": 1, "maximum": 30, "default": 7}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_inspection",
                    "description": "Start vibration inspection analysis",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "method": {"type": "string", "enum": ["auto", "cnn", "traditional"], "default": "auto"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_inspection_history",
                    "description": "Get recent inspection history",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_volume",
                    "description": "Set system volume",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "integer", "minimum": 0, "maximum": 100}
                        },
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_info",
                    "description": "Get system information",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
    
    def _register_tools(self):
        """Register tool implementations."""
        from desktop_bridge.main import (
            serial_manager, pc_monitor, music_controller, 
            calendar_service
        )
        from desktop_bridge.api.vibration import analyze_local_cnn
        from desktop_bridge.ml.traditional import analyze_traditional_features
        import numpy as np
        
        self._tool_functions = {
            "get_device_status": self._get_device_status,
            "switch_device_mode": self._switch_device_mode,
            "get_pc_metrics": self._get_pc_metrics,
            "control_music": self._control_music,
            "get_calendar_events": self._get_calendar_events,
            "run_inspection": self._run_inspection,
            "get_inspection_history": self._get_inspection_history,
            "set_volume": self._set_volume,
            "get_system_info": self._get_system_info,
        }
    
    async def initialize(self):
        """Initialize the voice assistant."""
        if not settings.nvidia_api_key:
            logger.warning("NVIDIA_API_KEY not set, voice assistant will not work")
            return
        
        self.client = AsyncOpenAI(
            base_url=settings.nemotron_base_url,
            api_key=settings.nvidia_api_key
        )
        logger.info("Voice assistant initialized")
    
    async def process_query(
        self, 
        text: str, 
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Process user query through Nemotron with tool calling."""
        if not self.client:
            return {"text": "Voice assistant not configured (missing NVIDIA_API_KEY)", "tool_calls": []}
        
        try:
            # Prepare messages
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful voice assistant for an Industrial Inspection "
                        "Desk Buddy device. You can control the device, check system status, "
                        "run inspections, control music, check calendar, and monitor PC health. "
                        "Be concise and helpful."
                    )
                },
                {"role": "user", "content": text}
            ]
            
            if context:
                messages.insert(1, {"role": "system", "content": f"Context: {json.dumps(context)}"})
            
            # Call Nemotron
            response = await self.client.chat.completions.create(
                model=settings.nemotron_model,
                messages=messages,
                tools=self._get_tools(),
                tool_choice="auto",
                temperature=0.1,
                max_tokens=1000
            )
            
            message = response.choices[0].message
            
            # Handle tool calls
            tool_results = []
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    if tool_name in self._tool_functions:
                        try:
                            result = await self._tool_functions[tool_name](**args)
                            tool_results.append({
                                "tool": tool_name,
                                "args": args,
                                "result": result
                            })
                        except Exception as e:
                            logger.error(f"Tool {tool_name} error: {e}")
                            tool_results.append({
                                "tool": tool_name,
                                "args": args,
                                "error": str(e)
                            })
            
            # If tools were called, get final response
            if tool_results:
                # Add tool results to conversation and get final response
                messages.append(message.model_dump())
                for tr in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tr["result"])
                    })
                
                final_response = await self.client.chat.completions.create(
                    model=settings.nemotron_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=500
                )
                
                final_text = final_response.choices[0].message.content
            else:
                final_text = message.content
            
            return {
                "text": final_text or "I understand.",
                "tool_calls": tool_results
            }
            
        except Exception as e:
            logger.error(f"Voice query error: {e}")
            return {"text": f"Error: {str(e)}", "tool_calls": []}
    
    # Tool implementations
    async def _get_device_status(self) -> Dict:
        from desktop_bridge.main import serial_manager
        
        if serial_manager and serial_manager.is_connected:
            return {
                "connected": True,
                "port": serial_manager.port,
                "sensors": {
                    "adxl345": "connected",
                    "bme280": "connected",
                    "oled": "connected",
                    "st7735": "connected"
                }
            }
        return {"connected": False}
    
    async def _switch_device_mode(self, mode: str) -> Dict:
        from desktop_bridge.main import serial_manager
        
        if not serial_manager or not serial_manager.is_connected:
            return {"error": "Device not connected"}
        
        success = await serial_manager.send_command("mode_switch", {"mode": mode})
        return {"success": success, "mode": mode}
    
    async def _get_pc_metrics(self) -> Dict:
        from desktop_bridge.main import pc_monitor
        
        if pc_monitor and pc_monitor.running:
            return pc_monitor.get_metrics()
        return {"error": "PC monitoring not available"}
    
    async def _control_music(self, action: str, level: Optional[int] = None) -> Dict:
        from desktop_bridge.main import music_controller
        
        if not music_controller or not music_controller.initialized:
            return {"error": "Music control not available"}
        
        try:
            if action == "play":
                await music_controller.play()
            elif action == "pause":
                await music_controller.pause()
            elif action == "next":
                await music_controller.next_track()
            elif action == "previous":
                await music_controller.previous_track()
            elif action == "volume" and level is not None:
                await music_controller.set_volume(level)
            
            return {"status": "ok", "action": action}
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_calendar_events(self, days: int = 7) -> Dict:
        from desktop_bridge.main import calendar_service
        
        if not calendar_service or not calendar_service.initialized:
            return {"error": "Calendar not available"}
        
        start = datetime.now()
        end = start + timedelta(days=days)
        events = await calendar_service.get_events(start, end)
        
        return {"events": [e.to_dict() for e in events]}
    
    async def _run_inspection(self, method: str = "auto") -> Dict:
        # This would trigger the device to capture vibration data
        # and send it for analysis
        from desktop_bridge.main import serial_manager
        
        if not serial_manager or not serial_manager.is_connected:
            return {"error": "Device not connected"}
        
        await serial_manager.send_command("start_inspection", {"method": method})
        
        return {"status": "started", "method": method}
    
    async def _get_inspection_history(self, limit: int = 10) -> Dict:
        # Would query backend or local storage
        return {"history": []}
    
    async def _set_volume(self, level: int) -> Dict:
        from desktop_bridge.main import music_controller
        
        if not music_controller or not music_controller.initialized:
            return {"error": "Music control not available"}
        
        await music_controller.set_volume(level)
        return {"status": "ok", "level": level}
    
    async def _get_system_info(self) -> Dict:
        import platform
        import psutil
        import socket
        
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2)
        }
    
    async def synthesize_speech(
        self, 
        text: str, 
        voice: str = "en-US-Neural",
        speed: float = 1.0
    ) -> bytes:
        """Text-to-speech synthesis (placeholder)."""
        # Would integrate with TTS service (Azure, Google, etc.)
        # Return audio bytes
        return b""
    
    async def transcribe_speech(self, audio_bytes: bytes) -> str:
        """Speech-to-text (placeholder for Whisper integration)."""
        # Would integrate with Whisper or similar
        return "Transcribed text"