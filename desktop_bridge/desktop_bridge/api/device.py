"""
Device Management API - Controls Arduino/ESP32 device.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
import asyncio

from desktop_bridge.config import settings
import desktop_bridge.main as main_module

router = APIRouter(prefix="/device", tags=["device"])


class DeviceStatus(BaseModel):
    connected: bool
    port: Optional[str] = None
    baudrate: int = 115200
    firmware_version: Optional[str] = None
    sensors: dict = {}


class ModeSwitchRequest(BaseModel):
    mode: str = Field(..., pattern="^(inspection|desk_buddy)$")


class CommandRequest(BaseModel):
    command: str
    payload: Optional[dict] = None


@router.get("/status", response_model=DeviceStatus)
async def get_device_status():
    """Get current device connection status."""
    sm = main_module.serial_manager
    connected = sm is not None and sm.is_connected
    
    return DeviceStatus(
        connected=connected,
        port=settings.serial_port if sm else None,
        baudrate=settings.serial_baudrate,
        firmware_version="1.0.0" if connected else None,
        sensors={
            "oled": "connected",
            "bme280": "connected",
            "adxl345": "connected",
            "st7735": "connected"
        } if connected else {}
    )


@router.get("/ports")
async def list_serial_ports():
    """List available serial ports."""
    from desktop_bridge.device.serial_manager import SerialManager
    ports = SerialManager.list_ports()
    return {"ports": ports}


@router.post("/connect")
async def connect_device(port: Optional[str] = None):
    """Connect to device on specified port."""
    import desktop_bridge.main as main_module
    from desktop_bridge.device.serial_manager import SerialManager
    
    # Check existing connection
    if main_module.serial_manager and main_module.serial_manager.is_connected:
        return {"status": "already_connected", "port": settings.serial_port}
    
    # Reinitialize serial manager
    new_manager = SerialManager(
        port=port or settings.serial_port,
        baudrate=settings.serial_baudrate,
        timeout=1.0
    )
    
    success = await new_manager.connect()
    if success:
        # Update the global reference in main module
        main_module.serial_manager = new_manager
        return {"status": "connected", "port": new_manager.port}
    else:
        raise HTTPException(status_code=500, detail="Failed to connect")


@router.post("/disconnect")
async def disconnect_device():
    """Disconnect from device."""
    sm = main_module.serial_manager
    if sm:
        await sm.disconnect()
        main_module.serial_manager = None
    
    return {"status": "disconnected"}


@router.post("/mode")
async def switch_mode(request: ModeSwitchRequest):
    """Switch device operating mode."""
    sm = main_module.serial_manager
    
    if not sm or not sm.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")
    
    success = await sm.send_command("mode_switch", {"mode": request.mode})
    
    if success:
        return {"status": "mode_switched", "mode": request.mode}
    else:
        raise HTTPException(status_code=500, detail="Failed to switch mode")


@router.post("/command")
async def send_command(request: CommandRequest):
    """Send raw command to device."""
    sm = main_module.serial_manager
    
    if not sm or not sm.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")
    
    success = await sm.send_command(request.command, request.payload)
    
    if success:
        return {"status": "sent", "command": request.command}
    else:
        raise HTTPException(status_code=500, detail="Failed to send command")


@router.get("/sensor-data")
async def get_sensor_data(sensor: Optional[str] = None):
    """Get latest sensor readings."""
    sm = main_module.serial_manager
    
    if not sm or not sm.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")
    
    # Request sensor data from device
    await sm.send_command("get_sensors", {"sensor": sensor} if sensor else {})
    
    # In a real implementation, this would wait for response
    # For now, return mock data
    return {
        "acceleration": {"x": 0.0, "y": 0.0, "z": 9.81},
        "temperature": 23.5,
        "humidity": 45.2,
        "pressure": 1013.25
    }


@router.post("/reset")
async def reset_device():
    """Reset device (send reset command)."""
    sm = main_module.serial_manager
    
    if not sm or not sm.is_connected:
        raise HTTPException(status_code=503, detail="Device not connected")
    
    await sm.send_command("reset", {})
    await asyncio.sleep(2)  # Wait for reset
    
    return {"status": "reset_sent"}