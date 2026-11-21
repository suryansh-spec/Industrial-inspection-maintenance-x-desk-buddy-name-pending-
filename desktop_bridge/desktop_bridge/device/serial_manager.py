"""
Serial Manager - Handles communication with Arduino/ESP32 via serial port.
"""
import asyncio
import logging
import serial
import serial.tools.list_ports
from typing import Optional, List, Dict, Any
import json

logger = logging.getLogger(__name__)


class SerialManager:
    """Manages serial communication with Arduino/ESP32."""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        self._connected = False
        self._read_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._command_queue: asyncio.Queue = asyncio.Queue()
        
    @property
    def is_connected(self) -> bool:
        return self._connected and self.serial is not None and self.serial.is_open
    
    async def connect(self) -> bool:
        """Establish serial connection."""
        try:
            # Try to find port if not found
            if not self._port_exists(self.port):
                logger.warning(f"Port {self.port} not found, scanning for alternatives...")
                ports = self._scan_ports()
                if ports:
                    self.port = ports[0]
                    logger.info(f"Using alternative port: {self.port}")
                else:
                    raise Exception("No serial ports found")
            
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=1.0
            )
            
            # Give Arduino time to reset
            await asyncio.sleep(2)
            
            # Clear buffers
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            self._connected = True
            logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Close serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self._connected = False
        logger.info("Serial disconnected")
    
    def _port_exists(self, port: str) -> bool:
        """Check if port exists."""
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return port in ports
    
    def _scan_ports(self) -> List[str]:
        """Scan for available serial ports."""
        ports = []
        for port in serial.tools.list_ports.comports():
            # Filter for common Arduino/ESP32 VID/PID
            if port.vid in [0x2341, 0x1A86, 0x10C4, 0x0403]:  # Arduino, CH340, CP2102, FTDI
                ports.append(port.device)
            elif "USB" in port.description or "UART" in port.description:
                ports.append(port.device)
        return ports
    
    async def send_command(self, command: str, payload: Optional[dict] = None) -> bool:
        """Send command to device."""
        if not self.is_connected:
            logger.warning("Not connected, cannot send command")
            return False
        
        try:
            message = {"cmd": command}
            if payload:
                message["payload"] = payload
            
            message_json = json.dumps(message) + "\n"
            self.serial.write(message_json.encode())
            self.serial.flush()
            logger.debug(f"Sent: {message_json.strip()}")
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False
    
    async def read_line(self) -> Optional[str]:
        """Read a line from serial."""
        if not self.is_connected:
            return None
        
        try:
            if self.serial.in_waiting > 0:
                line = self.serial.readline().decode('utf-8', errors='ignore').strip()
                return line if line else None
        except Exception as e:
            logger.error(f"Read error: {e}")
        return None
    
    async def write_raw(self, data: bytes) -> bool:
        """Write raw bytes to serial."""
        if not self.is_connected:
            return False
        try:
            self.serial.write(data)
            self.serial.flush()
            return True
        except Exception as e:
            logger.error(f"Write error: {e}")
            return False
    
    async def read_raw(self, size: int) -> Optional[bytes]:
        """Read raw bytes from serial."""
        if not self.is_connected:
            return None
        try:
            if self.serial.in_waiting >= size:
                return self.serial.read(size)
        except Exception as e:
            logger.error(f"Raw read error: {e}")
        return None
    
    @staticmethod
    def list_ports() -> List[Dict[str, Any]]:
        """List all available serial ports with details."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                "device": port.device,
                "name": port.name,
                "description": port.description,
                "vid": port.vid,
                "pid": port.pid,
                "manufacturer": port.manufacturer,
                "serial_number": port.serial_number
            })
        return ports