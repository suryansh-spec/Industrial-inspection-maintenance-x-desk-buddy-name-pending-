"""
Hardware Bridge Service - Communication with Arduino/ESP32 device.
"""
import asyncio
import logging
import json
import serial
import serial.tools.list_ports
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import time

from app.core.config import settings
from app.core.events import event_bus, EventType, Event
from app.models.hardware import Device, Sensor, SensorReading, InspectionSession

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SensorData:
    """Sensor data from device."""
    acceleration: Dict[str, float] = field(default_factory=dict)
    temperature: float = 0.0
    humidity: float = 0.0
    pressure: float = 0.0
    battery_voltage: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class DeviceCommand(Enum):
    MODE_SWITCH = "mode_switch"
    START_INSPECTION = "start_inspection"
    GET_SENSORS = "get_sensors"
    POMODORO_START = "pomodoro_start"
    POMODORO_PAUSE = "pomodoro_pause"
    POMODORO_RESET = "pomodoro_reset"
    PLAY_TONE = "play_tone"
    SET_VOLUME = "set_volume"
    GET_STATUS = "get_status"
    RESET = "reset"
    PLAY_MUSIC = "music_play"
    PAUSE_MUSIC = "music_pause"
    NEXT_TRACK = "music_next"
    PREV_TRACK = "music_prev"
    SET_BRIGHTNESS = "set_brightness"


class HardwareBridge:
    """
    Hardware bridge for communicating with Arduino/ESP32 device.
    Handles serial communication, command protocol, and data parsing.
    """
    
    def __init__(self):
        self.serial: Optional[serial.Serial] = None
        self.state = ConnectionState.DISCONNECTED
        self.port: Optional[str] = None
        self.baudrate = 115200
        self.timeout = 1.0
        
        # Device info
        self.device_id: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.device_mode: str = "desk_buddy"
        
        # Sensor data
        self.sensor_data: Dict[str, Any] = {}
        self.last_sensor_update: Optional[datetime] = None
        
        # Callbacks
        self.on_sensor_data: Optional[Callable] = None
        self.on_mode_change: Optional[Callable] = None
        self.on_notification: Optional[Callable] = None
        self.on_pomodoro_update: Optional[Callable] = None
        self.on_inspection_result: Optional[Callable] = None
        
        # Internal
        self._serial: Optional[serial.Serial] = None
        self._read_task: Optional[asyncio.Task] = None
        self._running = False
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._response_futures: Dict[str, asyncio.Future] = {}
        self._command_id = 0
        
        # Buffer for incomplete lines
        self._buffer = ""
    
    async def connect(self, port: Optional[str] = None) -> bool:
        """Connect to the device."""
        if self.state == ConnectionState.CONNECTED:
            logger.warning("Already connected")
            return True
        
        self.state = ConnectionState.CONNECTING
        target_port = port or self._find_device_port()
        
        if not target_port:
            logger.error("No device port found")
            self.state = ConnectionState.ERROR
            return False
        
        try:
            self._serial = serial.Serial(
                port=target_port,
                baudrate=115200,
                timeout=1.0,
                write_timeout=1.0
            )
            
            # Wait for device to settle
            await asyncio.sleep(2)
            
            # Clear buffers
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            
            self.port = target_port
            self.state = ConnectionState.CONNECTED
            self._running = True
            
            # Start read task
            self._read_task = asyncio.create_task(self._read_loop())
            
            # Wait for device ready
            await asyncio.sleep(1)
            
            # Request device info
            await self._request_device_info()
            
            logger.info(f"Connected to device on {target_port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.state = ConnectionState.ERROR
            return False
    
    def _find_device_port(self) -> Optional[str]:
        """Auto-detect device port."""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            # Filter for common ESP32/Arduino VID/PID
            if port.vid in [0x2341, 0x1A86, 0x10C4, 0x0403]:  # Arduino, CH340, CP2102, FTDI
                return port.device
            if "USB" in port.description or "UART" in port.description:
                return port.device
        return None
    
    async def disconnect(self):
        """Disconnect from device."""
        self._running = False
        
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        
        if self._serial and self._serial.is_open:
            self._serial.close()
        
        self.state = ConnectionState.DISCONNECTED
        logger.info("Disconnected from device")
    
    async def _read_loop(self):
        """Continuously read from serial port."""
        while self._running and self._serial and self._serial.is_open:
            try:
                if self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        await self._process_line(line)
                else:
                    await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Read error: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_line(self, line: str):
        """Process a line from serial."""
        line = line.strip()
        if not line:
            return
        
        logger.debug(f"RX: {line}")
        
        # Try to parse as JSON
        try:
            data = json.loads(line)
            await self._handle_json_message(data)
            return
        except json.JSONDecodeError:
            pass
        
        # Handle plain text responses
        if line.startswith("OK") or line.startswith("ERROR"):
            await self._handle_response(line)
        elif line.startswith("{"):
            # Might be incomplete JSON
            self._buffer += line
            try:
                data = json.loads(self._buffer)
                self._buffer = ""
                await self._handle_json_message(data)
            except json.JSONDecodeError:
                pass  # Wait for more data
        else:
            # Log other messages
            logger.debug(f"Device: {line}")
    
    async def _handle_json_message(self, data: dict):
        """Handle parsed JSON message from device."""
        msg_type = data.get("type") or data.get("cmd")
        
        if msg_type == "sensor_data":
            await self._handle_sensor_data(data.get("data", {}))
        elif msg_type == "mode_switched":
            await self._handle_mode_change(data.get("payload", ""))
        elif msg_type == "inspection_started":
            logger.info("Inspection started")
        elif msg_type == "inspection_completed":
            await self._handle_inspection_result(data.get("payload", {}))
        elif msg_type == "pomodoro":
            await self._handle_pomodoro_update(data.get("payload", ""))
        elif msg_type == "notification":
            await self._handle_notification(data)
        elif msg_type == "sensor_data":
            await self._handle_sensor_data(data.get("data", {}))
        elif msg_type == "pong":
            pass  # Heartbeat response
        elif msg_type == "status":
            logger.info(f"Device status: {data.get('payload', '')}")
        else:
            logger.debug(f"Unhandled message type: {msg_type}")
    
    async def _handle_sensor_data(self, data: dict):
        """Handle sensor data from device."""
        sensor_data = {
            "acceleration": data.get("accel", {}),
            "temperature": data.get("temp", 0),
            "humidity": data.get("humidity", 0),
            "pressure": data.get("pressure", 0),
            "battery": data.get("battery", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.sensor_data = sensor_data
        self.last_sensor_update = datetime.utcnow()
        
        # Emit event
        from app.core.events import event_bus, EventType, Event
        await event_bus.publish(Event(
            type=EventType.DEVICE_SENSOR_DATA,
            data=sensor_data,
            source="hardware_bridge"
        ))
        
        # Call callback
        if self.on_sensor_data:
            await self.on_sensor_data(sensor_data)
    
    async def _handle_mode_change(self, mode: str):
        """Handle mode change from device."""
        self.device_mode = mode
        logger.info(f"Device mode changed to: {mode}")
        
        if self.on_mode_change:
            await self.on_mode_change(mode)
    
    async def _handle_pomodoro_update(self, event: str):
        """Handle Pomodoro state updates."""
        logger.info(f"Pomodoro event: {event}")
        
        if self.on_pomodoro_update:
            await self.on_pomodoro_update(event)
    
    async def _handle_inspection_result(self, payload: dict):
        """Handle inspection result from device."""
        logger.info(f"Inspection result: {payload}")
        
        if self.on_inspection_result:
            await self.on_inspection_result(payload)
    
    async def _handle_notification(self, data: dict):
        """Handle notification from device."""
        title = data.get("title", "")
        message = data.get("message", "")
        priority = data.get("priority", 1)
        
        if self.on_notification:
            await self.on_notification({
                "title": title,
                "message": message,
                "priority": priority
            })
    
    async def _handle_response(self, line: str):
        """Handle simple text response."""
        # Handle OK/ERROR responses
        pass
    
    async def _request_device_info(self):
        """Request device information."""
        await self.send_command("get_sensors", {})
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    async def send_command(self, command: str, payload: Optional[dict] = None) -> bool:
        """Send command to device."""
        if not self.state == ConnectionState.CONNECTED:
            logger.warning("Not connected to device")
            return False
        
        try:
            message = {"cmd": command}
            if payload:
                message["payload"] = payload
            
            message_json = json.dumps(message) + "\n"
            self._serial.write(message_json.encode())
            self._serial.flush()
            
            logger.debug(f"TX: {message_json.strip()}")
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False
    
    async def send_command_with_response(
        self, command: str, payload: Optional[dict] = None, timeout: float = 5.0
    ) -> Optional[dict]:
        """Send command and wait for response."""
        self._command_id += 1
        cmd_id = f"cmd_{self._command_id}"
        
        future = asyncio.Future()
        self._response_futures[cmd_id] = future
        
        payload = payload or {}
        payload["cmd_id"] = cmd_id
        
        await self.send_command(command, payload)
        
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Command {command} timed out")
            return None
        finally:
            self._response_futures.pop(cmd_id, None)
    
    async def _handle_response(self, line: str):
        """Handle command response."""
        # Parse response and resolve future
        pass
    
    # ========================================================================
    # HIGH-LEVEL COMMANDS
    # ========================================================================
    
    async def switch_mode(self, mode: str) -> bool:
        """Switch device mode."""
        if mode not in ["inspection", "desk_buddy"]:
            raise ValueError("Invalid mode")
        
        return await self.send_command("mode_switch", {"mode": mode})
    
    async def start_inspection(self, method: str = "auto") -> bool:
        """Start inspection on device."""
        return await self.send_command("start_inspection", {"method": method})
    
    async def get_sensor_data(self) -> Optional[dict]:
        """Request current sensor data."""
        return await self.send_command_with_response("get_sensors", {}, timeout=3.0)
    
    async def start_pomodoro(self) -> bool:
        return await self.send_command("pomodoro", {"action": "start"})
    
    async def pause_pomodoro(self) -> bool:
        return await self.send_command("pomodoro", {"action": "pause"})
    
    async def reset_pomodoro(self) -> bool:
        return await self.send_command("pomodoro", {"action": "reset"})
    
    async def play_tone(self, frequency: int, duration: int) -> bool:
        return await self.send_command("play_tone", {"frequency": frequency, "duration": duration})
    
    async def set_volume(self, level: int) -> bool:
        return await self.send_command("set_volume", {"level": max(0, min(100, level))})
    
    async def get_status(self) -> Optional[dict]:
        return await self.send_command_with_response("get_status", {}, timeout=3.0)
    
    async def reset_device(self) -> bool:
        return await self.send_command("reset", {})
    
    async def control_music(self, action: str, level: Optional[int] = None) -> bool:
        """Control music playback."""
        payload = {"action": action}
        if level is not None:
            payload["level"] = level
        return await self.send_command("music", payload)
    
    async def switch_page(self, page: int) -> bool:
        """Switch display page (0-5)."""
        if 0 <= page < 6:
            return await self.send_command("page", {"page": page})
        return False
    
    async def send_notification(self, title: str, message: str, priority: int = 1) -> bool:
        """Send notification to device display."""
        return await self.send_command("notification", {
            "title": title,
            "message": message,
            "priority": priority
        })
    
    async def set_brightness(self, level: int) -> bool:
        """Set display brightness (0-255)."""
        level = max(0, min(255, level))
        return await self.send_command("brightness", {"level": level})
    
    # ========================================================================
    # INSPECTION WORKFLOW
    # ========================================================================
    
    async def run_inspection(
        self,
        method: str = "auto",
        duration_seconds: int = 10,
        callback: Optional[Callable] = None
    ) -> Optional[dict]:
        """
        Run a complete inspection workflow.
        
        Args:
            method: "auto", "cnn", "traditional", "both"
            duration_seconds: How long to capture data
            callback: Optional callback for progress updates
        
        Returns:
            Inspection result dict or None if failed
        """
        if not self.state == ConnectionState.CONNECTED:
            logger.error("Device not connected")
            return None
        
        try:
            # Switch to inspection mode
            await self.switch_mode("inspection")
            await asyncio.sleep(1)
            
            # Start inspection
            await self.start_inspection(method)
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < duration_seconds + 30:  # Extra time for processing
                if callback:
                    await callback({"progress": min(100, int((time.time() - start_time) / duration_seconds * 100))})
                
                await asyncio.sleep(1)
                
                # Check for result
                status = await self.get_status()
                if status and status.get("inspection_complete"):
                    return status.get("result")
            
            logger.warning("Inspection timed out")
            return None
            
        except Exception as e:
            logger.error(f"Inspection failed: {e}")
            return None
    
    # ========================================================================
    # STATUS
    # ========================================================================
    
    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED
    
    def get_sensor_data(self) -> Dict[str, Any]:
        return asdict(self.sensor_data)
    
    def get_device_info(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "port": self.port,
            "mode": self.device_mode,
            "firmware": self.firmware_version,
            "last_sensor_update": self.last_sensor_update.isoformat() if self.last_sensor_update else None,
            "sensor_data": self.sensor_data
        }


# Global instance
hardware_bridge = HardwareBridge()