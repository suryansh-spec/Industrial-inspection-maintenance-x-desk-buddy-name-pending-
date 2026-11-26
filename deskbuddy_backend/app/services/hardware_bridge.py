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
        self._write_lock = asyncio.Lock()
        self._rx_buf = bytearray()
        self._inbound_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        self._manual_disconnect = False
        self._ws = None  # FastAPI WebSocket when the device is attached wirelessly

        # Buffer for incomplete lines
        self._buffer = ""

    async def connect(self, port: Optional[str] = None) -> bool:
        """Connect to the device."""
        if self.state == ConnectionState.CONNECTED:
            logger.warning("Already connected")
            return True

        self._manual_disconnect = False
        self.state = ConnectionState.CONNECTING
        target_port = port or self._find_device_port()

        if not target_port:
            logger.error("No device port found")
            self.state = ConnectionState.ERROR
            return False

        try:
            def _open_port():
                ser = serial.Serial(
                    port=target_port,
                    baudrate=115200,
                    timeout=1.0,
                    write_timeout=1.0,
                )
                return ser

            self._serial = await asyncio.to_thread(_open_port)

            # Wait for device to settle
            await asyncio.sleep(2)

            # Clear buffers
            await asyncio.to_thread(self._serial.reset_input_buffer)
            await asyncio.to_thread(self._serial.reset_output_buffer)

            self.port = target_port
            self.state = ConnectionState.CONNECTED
            self._running = True
            self._rx_buf.clear()

            from app.services import serial_manager as serial_state
            serial_state.set_serial_manager(self)

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
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
            self.state = ConnectionState.ERROR
            return False
    
    async def attach_websocket(self, ws) -> None:
        """Use an already-accepted WebSocket as the device transport.

        This is the wireless/cloud path: the ESP32 mirrors its USB-serial JSON
        protocol over ``wss://<host>/ws/device``. Blocks until the socket closes.
        """
        from fastapi import WebSocketDisconnect

        if self.state == ConnectionState.CONNECTED:
            await self.disconnect()

        self._manual_disconnect = False
        self._ws = ws
        self.port = "websocket"
        self.state = ConnectionState.CONNECTED
        self._running = True
        self._rx_buf.clear()

        from app.services import serial_manager as serial_state
        serial_state.set_serial_manager(self)
        logger.info("Device attached over WebSocket")

        try:
            while True:
                text = await ws.receive_text()
                for raw in text.splitlines():
                    line = raw.strip()
                    if line:
                        await self._process_line(line)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("Device WebSocket closed: %s", exc)
        finally:
            # Only tear down if this is still the active session.
            if self._ws is ws:
                self._ws = None
                self._running = False
                self.port = None
                self.state = ConnectionState.DISCONNECTED
                if serial_state.get_serial_manager() is self:
                    serial_state.set_serial_manager(None)
                logger.info("Device WebSocket detached")

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
    
    async def disconnect(self, manual: bool = False):
        """Disconnect from device."""
        if manual:
            self._manual_disconnect = True
        self._running = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._serial and self._serial.is_open:
            try:
                await asyncio.to_thread(self._serial.close)
            except Exception:
                pass
        self._serial = None

        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

        from app.services import serial_manager as serial_state
        if serial_state.get_serial_manager() is self:
            serial_state.set_serial_manager(None)

        self.state = ConnectionState.DISCONNECTED
        logger.info("Disconnected from device")

    def _read_available_sync(self) -> bytes:
        """Read currently buffered bytes from serial without blocking on incomplete lines."""
        if not self._serial or not self._serial.is_open:
            return b""
        waiting = self._serial.in_waiting
        if waiting > 0:
            return self._serial.read(waiting)
        return b""

    async def read_line(self) -> Optional[str]:
        """Non-blocking pop of the next complete line for external consumers."""
        try:
            return self._inbound_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def _enqueue_inbound(self, line: str) -> None:
        if self._inbound_queue.full():
            try:
                self._inbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._inbound_queue.put_nowait(line)
        except asyncio.QueueFull:
            pass

    async def _read_loop(self):
        """Continuously read from serial port."""
        while self._running and self._serial and self._serial.is_open:
            try:
                chunk = await asyncio.to_thread(self._read_available_sync)
                if chunk:
                    self._rx_buf.extend(chunk)
                    if len(self._rx_buf) > 32768:
                        self._rx_buf = self._rx_buf[-16384:]
                    while b"\n" in self._rx_buf:
                        raw_line, _, rest = self._rx_buf.partition(b"\n")
                        self._rx_buf = bytearray(rest)
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if line:
                            await self._process_line(line)
                else:
                    await asyncio.sleep(0.01)
            except serial.SerialException as e:
                logger.error(f"Serial connection lost: {e}")
                self._running = False
                if self._serial and self._serial.is_open:
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                self._serial = None
                from app.services import serial_manager as serial_state
                if serial_state.get_serial_manager() is self:
                    serial_state.set_serial_manager(None)
                self.state = ConnectionState.DISCONNECTED
                break
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
            self._buffer = ""
            self._enqueue_inbound(line)
            await self._handle_json_message(data)
            return
        except json.JSONDecodeError:
            pass

        # Handle plain text responses
        if line.startswith("OK") or line.startswith("ERROR"):
            self._enqueue_inbound(line)
            await self._handle_response(line)
        elif line.startswith("{") or self._buffer:
            # Might be incomplete JSON
            if line.startswith("{") and self._buffer:
                self._buffer = ""
            self._buffer += line
            if len(self._buffer) > 16384:
                self._buffer = ""
                return
            try:
                data = json.loads(self._buffer)
                full_line = self._buffer
                self._buffer = ""
                self._enqueue_inbound(full_line)
                await self._handle_json_message(data)
            except json.JSONDecodeError:
                pass  # Wait for more data
        else:
            self._enqueue_inbound(line)
            logger.debug(f"Device: {line}")

    async def _handle_json_message(self, data: dict):
        """Handle parsed JSON message from device."""
        msg_type = data.get("type") or data.get("cmd")

        payload_obj = data.get("payload")
        cmd_id = data.get("cmd_id") or (payload_obj.get("cmd_id") if isinstance(payload_obj, dict) else None)
        if cmd_id and cmd_id in self._response_futures:
            fut = self._response_futures[cmd_id]
            if not fut.done():
                fut.set_result(data)

        if msg_type == "sensor_data":
            await self._handle_sensor_data(data.get("data", {}))
        elif msg_type == "heartbeat":
            if data.get("firmware"):
                self.firmware_version = str(data["firmware"])
            if data.get("mode"):
                self.device_mode = str(data["mode"])
        elif msg_type == "mode_switched":
            mode = data.get("mode") or (payload_obj if isinstance(payload_obj, str) else "")
            await self._handle_mode_change(mode)
        elif msg_type == "inspection_started":
            logger.info("Inspection started")
        elif msg_type in ("inspection_completed", "inspection_data"):
            await self._handle_inspection_result(data.get("data") or (payload_obj if isinstance(payload_obj, dict) else {}))
        elif msg_type == "pomodoro":
            action = data.get("action") or (payload_obj if isinstance(payload_obj, str) else "")
            await self._handle_pomodoro_update(action)
        elif msg_type == "notification":
            await self._handle_notification(data)
        elif msg_type == "pong":
            pass  # Heartbeat response
        elif msg_type == "status":
            if data.get("firmware"):
                self.firmware_version = str(data["firmware"])
            if data.get("mode"):
                self.device_mode = str(data["mode"])
            logger.info(f"Device status: {data.get('payload', data)}")
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
    
    async def _request_device_info(self):
        """Request device information."""
        await self.send_command("get_sensors", {})
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    async def send_command(self, command: str, payload: Optional[dict] = None) -> bool:
        """Send command to device."""
        has_ws = self._ws is not None
        if not self.state == ConnectionState.CONNECTED or (
            not has_ws and (not self._serial or not self._serial.is_open)
        ):
            logger.warning("Not connected to device")
            return False

        try:
            message = {"cmd": command}
            if payload:
                message["payload"] = payload

            message_json = json.dumps(message) + "\n"
            encoded = message_json.encode()

            if has_ws:
                async with self._write_lock:
                    await self._ws.send_text(message_json)
                logger.debug(f"TX(ws): {message_json.strip()}")
                return True

            def _write_sync():
                self._serial.write(encoded)
                self._serial.flush()

            async with self._write_lock:
                await asyncio.to_thread(_write_sync)

            logger.debug(f"TX: {message_json.strip()}")
            return True
        except serial.SerialException as e:
            logger.error(f"Send error (serial disconnected): {e}")
            self.state = ConnectionState.DISCONNECTED
            return False
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False
    
    async def send_command_with_response(
        self, command: str, payload: Optional[dict] = None, timeout: float = 5.0
    ) -> Optional[dict]:
        """Send command and wait for response."""
        self._command_id += 1
        cmd_id = f"cmd_{self._command_id}"
        
        future = asyncio.get_running_loop().create_future()
        self._response_futures[cmd_id] = future
        
        payload = dict(payload) if payload else {}
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
        """Handle simple text response."""
        for cmd_id, fut in list(self._response_futures.items()):
            if not fut.done():
                fut.set_result({"ok": line.startswith("OK"), "raw": line})
                break
    
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
    
    def get_cached_sensor_data(self) -> Dict[str, Any]:
        return dict(self.sensor_data)
    
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