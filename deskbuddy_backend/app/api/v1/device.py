"""
Device Management API endpoints.
"""
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.companion import companion_service
from app.services.hardware_bridge import hardware_bridge

router = APIRouter(prefix="/device", tags=["device"])


class DeviceStatus(BaseModel):
    connected: bool
    port: Optional[str] = None
    baudrate: int = 115200
    firmware_version: Optional[str] = None
    sensors: Dict[str, Any] = {}


class ModeSwitchRequest(BaseModel):
    mode: str = Field(..., pattern="^(inspection|desk_buddy)$")


class CommandRequest(BaseModel):
    command: str
    payload: Optional[Dict[str, Any]] = None


@router.get("/status", response_model=DeviceStatus)
async def get_device_status():
    """Get current device connection status."""
    connected = hardware_bridge.is_connected
    return DeviceStatus(
        connected=connected,
        port=hardware_bridge.port if connected else None,
        baudrate=115200,
        firmware_version=hardware_bridge.firmware_version if connected else None,
        sensors=hardware_bridge.get_cached_sensor_data() if connected else {},
    )


@router.post("/connect")
async def connect_device(port: Optional[str] = None):
    """Connect to device on specified port."""
    if hardware_bridge.is_connected:
        return {"status": "already_connected", "port": hardware_bridge.port}

    success = await hardware_bridge.connect(port)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect")

    companion_service.touch_device()

    # Re-apply the panel-owned settings (theme, buttons, font, wallpaper) so the
    # device comes back exactly as the user left it, even after a re-flash.
    try:
        from app.services.device_settings import push_all
        await push_all(hardware_bridge)
    except Exception:  # pragma: no cover - hardware dependent
        pass

    return {"status": "connected", "port": hardware_bridge.port}


@router.post("/disconnect")
async def disconnect_device():
    """Disconnect from device."""
    await hardware_bridge.disconnect(manual=True)
    return {"status": "disconnected"}


@router.post("/mode")
async def switch_mode(request: ModeSwitchRequest):
    """Switch device operating mode."""
    if not hardware_bridge.is_connected:
        raise HTTPException(status_code=503, detail="Device is not connected")
    success = await hardware_bridge.send_command("mode_switch", {"mode": request.mode})
    if not success:
        raise HTTPException(status_code=500, detail="Failed to switch mode")
    return {"status": "switched", "mode": request.mode}


@router.post("/command")
async def send_command(request: CommandRequest):
    """Send arbitrary command to device."""
    if not hardware_bridge.is_connected:
        raise HTTPException(status_code=503, detail="Device is not connected")
    success = await hardware_bridge.send_command(request.command, request.payload)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send command")
    return {"status": "sent", "command": request.command}


@router.get("/info")
async def get_device_info():
    """Get detailed device information."""
    if not hardware_bridge.is_connected:
        raise HTTPException(status_code=503, detail="Device is not connected")
    return hardware_bridge.get_device_info()