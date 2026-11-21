"""
Serial manager for the ESP32-S3 Desk Buddy.

Kept inside the backend package so the API does not depend on the
standalone ``desktop_bridge`` package being importable.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)


class SerialManager:
    """Manages serial communication with the Arduino/ESP32 device."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.serial is not None and self.serial.is_open

    async def connect(self) -> bool:
        """Establish the serial connection."""
        try:
            if not self._port_exists(self.port):
                logger.warning("Port %s not found, scanning for alternatives...", self.port)
                ports = self._scan_ports()
                if ports:
                    self.port = ports[0]
                    logger.info("Using alternative port: %s", self.port)
                else:
                    raise RuntimeError("No serial ports found")

            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=1.0,
            )

            # Give the Arduino time to reset after opening the port.
            await asyncio.sleep(2)

            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

            self._connected = True
            logger.info("Connected to %s at %s baud", self.port, self.baudrate)
            return True

        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.error("Failed to connect to %s: %s", self.port, exc)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self._connected = False
        logger.info("Serial disconnected")

    def _port_exists(self, port: str) -> bool:
        return port in [p.device for p in serial.tools.list_ports.comports()]

    def _scan_ports(self) -> List[str]:
        ports: List[str] = []
        for port in serial.tools.list_ports.comports():
            if port.vid in (0x2341, 0x1A86, 0x10C4, 0x0403):
                ports.append(port.device)
            elif "USB" in (port.description or "") or "UART" in (port.description or ""):
                ports.append(port.device)
        return ports

    async def send_command(self, command: str, payload: Optional[dict] = None) -> bool:
        """Send a JSON command to the device."""
        if not self.is_connected:
            logger.warning("Not connected, cannot send command")
            return False

        try:
            message: Dict[str, Any] = {"cmd": command}
            if payload:
                message["payload"] = payload

            message_json = json.dumps(message) + "\n"
            self.serial.write(message_json.encode())
            self.serial.flush()
            logger.debug("Sent: %s", message_json.strip())
            return True
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.error("Send error: %s", exc)
            return False

    async def read_line(self) -> Optional[str]:
        """Read a single line from the serial port."""
        if not self.is_connected:
            return None

        try:
            if self.serial.in_waiting > 0:
                line = self.serial.readline().decode("utf-8", errors="ignore").strip()
                return line if line else None
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.error("Read error: %s", exc)
        return None

    async def write_raw(self, data: bytes) -> bool:
        """Write raw bytes to the serial port."""
        if not self.is_connected:
            return False
        try:
            self.serial.write(data)
            self.serial.flush()
            return True
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.error("Write error: %s", exc)
            return False

    async def read_raw(self, size: int) -> Optional[bytes]:
        """Read raw bytes from the serial port."""
        if not self.is_connected:
            return None
        try:
            if self.serial.in_waiting >= size:
                return self.serial.read(size)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.error("Raw read error: %s", exc)
        return None

    @staticmethod
    def list_ports() -> List[Dict[str, Any]]:
        """List available serial ports with details."""
        return [
            {
                "device": port.device,
                "name": port.name,
                "description": port.description,
                "vid": port.vid,
                "pid": port.pid,
                "manufacturer": port.manufacturer,
                "serial_number": port.serial_number,
            }
            for port in serial.tools.list_ports.comports()
        ]


# Active connection, set by the API or the application lifespan.
serial_manager: Optional[SerialManager] = None


def get_serial_manager() -> Optional[SerialManager]:
    """Return the active serial manager (or ``None``)."""
    return serial_manager


def set_serial_manager(manager: Optional[SerialManager]) -> None:
    """Replace the active serial manager."""
    global serial_manager
    serial_manager = manager
