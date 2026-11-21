"""
Device Management API endpoints.
"""
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services import serial_manager as serial_state
from app.services.companion import companion_service
from app.services.serial_manager import SerialManager

router = APIRouter(prefix="/device", tags=["device"])


class DeviceStatus(BaseModel):
    connected: bool
    port: Optional[str] = None
    baudrate: int = 115200
    firmware_version: Optional[str] = None
    sensors: Dict[str, str] = {}


class ModeSwitchRequest(BaseModel):
    mode: str = Field(..., pattern="^(inspection|desk_buddy)$")


class CommandRequest(BaseModel):
    command: str
    payload: Optional[Dict[str, Any]] = None


@router.get("/status", response_model=DeviceStatus)
async def get_device_status():
    """Get current device connection status."""
    manager = serial_state.get_serial_manager()
    connected = manager is not None and manager.is_connected

    return DeviceStatus(
        connected=connected,
        port=manager.port if manager else None,
        baudrate=settings.serial_baudrate,
        firmware_version="1.0.0" if connected else None,
        sensors={
            "oled": "connected",
            "bme280": "connected",
            "adxl345": "connected",
            "st7735": "connected",
        } if connected else {},
    )


@router.get("/ports")
async def list_serial_ports():
    """List available serial ports."""
    return {"ports": SerialManager.list_ports()}


@router.post("/connect")
async def connect_device(port: Optional[str] = None):
    """Connect to device on specified port."""
    manager = serial_state.get_serial_manager()

    if manager and manager.is_connected:
        return {"status": "already_connected", "port": manager.port}

    manager = SerialManager(
        port=port or settings.serial_port,
        baudrate=settings.serial_baudrate,
        timeout=settings.serial_timeout,
    )

    success = await manager.connect()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect")

    serial_state.set_serial_manager(manager)
    companion_service.touch_device()

    # Re-apply the panel-owned settings (theme, buttons, font, wallpaper) so the
    # device comes back exactly as the user left it, even after a re-flash.
    try:
        from app.services.device_settings import push_all
        await push_all(manager)
    except Exception:  # pragma: no cover - hardware dependent
        pass

    return {"status": "connected", "port": manager.port}


@router.post("/disconnect")
async def disconnect_device():
    """Disconnect from device."""
    manager = serial_state.get_serial_manager()
    if manager:
        await manager.disconnect()
        serial_state.set_serial_manager(None)

    return {"status": "disconnected"}


@router.post("/mode")
async def switch_mode(request: ModeSwitchRequest):
    """Switch device operating mode."""
    manager = serial_state.get_serial_manager()
    if not manager or not manager.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")

    success = await manager.send_command("mode_switch", {"mode": request.mode})
    if not success:
        raise HTTPException(status_code=500, detail="Failed to switch mode")

    return {"status": "mode_switched", "mode": request.mode}


@router.post("/command")
async def send_command(request: CommandRequest):
    """Send raw command to device."""
    manager = serial_state.get_serial_manager()
    if not manager or not manager.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")

    success = await manager.send_command(request.command, request.payload)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send command")

    return {"status": "sent", "command": request.command}


@router.get("/sensor-data")
async def get_sensor_data(sensor: Optional[str] = None):
    """Request the latest sensor readings."""
    manager = serial_state.get_serial_manager()
    if not manager or not manager.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")

    await manager.send_command("get_sensors", {"sensor": sensor} if sensor else {})
    return {"status": "requested"}


@router.post("/reset")
async def reset_device():
    """Reset device (send reset command)."""
    manager = serial_state.get_serial_manager()
    if not manager or not manager.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")

    await manager.send_command("reset", {})
    await asyncio.sleep(2)

    return {"status": "reset_sent"}


@router.get("/info")
async def get_device_info():
    """Get detailed device information."""
    manager = serial_state.get_serial_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Device not connected")

    if manager.is_connected:
        return {
            "connected": True,
            "port": manager.port,
            "baudrate": manager.baudrate,
            "firmware_version": "1.0.0",
            "sensors": ["adxl345", "bme280", "oled", "st7735"],
        }
    return {"connected": False}
