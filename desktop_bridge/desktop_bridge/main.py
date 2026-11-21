"""
Desktop Bridge - Main Application Entry Point.

Central integration layer connecting:
- Arduino/ESP32 (Serial/HTTP)
- FastAPI Backend API
- ML Pipeline (CNN + Traditional)
- Desktop Tools (PC monitoring, Music, Calendar, Voice)
- Nemotron Voice Assistant
- DeskMate Desktop Companion
"""
import asyncio
import json
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from desktop_bridge.config import settings, PROJECT_ROOT
from desktop_bridge.device.serial_manager import SerialManager
from desktop_bridge.api.vibration import router as vibration_router
from desktop_bridge.api.device import router as device_router
from desktop_bridge.api.desktop_tools import router as desktop_tools_router
from desktop_bridge.api.voice import router as voice_router
from desktop_bridge.ws.manager import ConnectionManager
from desktop_bridge.services.pc_monitor import PCMonitor
from desktop_bridge.services.music import MusicController
from desktop_bridge.services.calendar import CalendarService
from desktop_bridge.services.deskmate import DeskMateService, create_deskbuddy_services

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.bridge_debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "logs" / "desktop_bridge.log")
    ]
)
logger = logging.getLogger(__name__)


# Global services
serial_manager: Optional[SerialManager] = None
pc_monitor: Optional[PCMonitor] = None
music_controller: Optional[MusicController] = None
calendar_service: Optional[CalendarService] = None
deskmate_service: Optional["DeskMateService"] = None
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - startup and shutdown."""
    global serial_manager, pc_monitor, music_controller, calendar_service, deskmate_service
    
    logger.info("Starting Desktop Bridge...")
    
    # Initialize services
    try:
        # Serial connection to Arduino/ESP32
        serial_manager = SerialManager(
            port=settings.serial_port,
            baudrate=settings.serial_baudrate,
            timeout=settings.serial_timeout
        )
        await serial_manager.connect()
        logger.info(f"Serial connected on {settings.serial_port}")
    except Exception as e:
        logger.warning(f"Serial connection failed: {e}. Running without hardware.")
        serial_manager = None
    
    # PC Monitoring
    if settings.enable_pc_monitoring:
        pc_monitor = PCMonitor()
        await pc_monitor.start()
        logger.info("PC monitoring started")
    
    # Music Controller
    if settings.enable_music_control:
        music_controller = MusicController()
        await music_controller.initialize()
        logger.info("Music controller initialized")
    
    # Calendar Service
    if settings.enable_calendar:
        calendar_service = CalendarService()
        await calendar_service.initialize()
        logger.info("Calendar service initialized")
    
    # DeskMate Desktop Companion
    if settings.enable_desk_mate:
        deskmate_services = create_deskbuddy_services()
        global deskmate_service
        deskmate_service = deskmate_services["deskmate"]
        await deskmate_service.initialize()
        
        # Connect DeskMate callbacks to bridge
        deskmate_service.on_notification = lambda n: asyncio.create_task(ws_manager.broadcast("notifications", {
            "type": "notification",
            "data": {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "priority": n.priority.value,
                "category": n.category,
                "timestamp": n.timestamp.isoformat(),
                "actions": n.actions
            }
        }))
        deskmate_service.on_pomodoro_tick = lambda rem, is_break: asyncio.create_task(ws_manager.broadcast("pomodoro", {
            "type": "tick", "remaining": rem, "is_break": is_break
        }))
        deskmate_service.on_pomodoro_complete = lambda event: asyncio.create_task(ws_manager.broadcast("pomodoro", {
            "type": "complete", "event": event
        }))
        deskmate_service.on_clipboard_change = lambda history: asyncio.create_task(ws_manager.broadcast("clipboard", {
            "type": "history_update", "data": history
        }))
        
        logger.info("DeskMate Desktop Companion initialized")
    
    # Start background tasks
    asyncio.create_task(ws_heartbeat_task())
    asyncio.create_task(serial_read_task())
    asyncio.create_task(pc_metrics_broadcast_task())
    
    logger.info("Desktop Bridge started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Desktop Bridge...")
    
    if serial_manager:
        await serial_manager.disconnect()
    if pc_monitor:
        await pc_monitor.stop()
    if music_controller:
        await music_controller.cleanup()
    if calendar_service:
        await calendar_service.cleanup()
    if deskmate_service:
        await deskmate_service.cleanup()
    
    logger.info("Desktop Bridge stopped")


app = FastAPI(
    title="Desktop Bridge",
    description="Central integration layer for Inspection Desk Buddy",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(vibration_router, prefix="/api/v1/inspect", tags=["inspection"])
app.include_router(device_router, prefix="/api/v1/device", tags=["device"])
app.include_router(desktop_tools_router, prefix="/api/v1/desktop", tags=["desktop"])
app.include_router(voice_router, prefix="/api/v1/voice", tags=["voice"])


@app.get("/")
async def root():
    return {
        "service": "Desktop Bridge",
        "version": "1.0.0",
        "status": "running",
        "hardware_connected": serial_manager is not None and serial_manager.is_connected,
        "endpoints": {
            "inspection": "/api/v1/inspect",
            "device": "/api/v1/device",
            "desktop": "/api/v1/desktop",
            "voice": "/api/v1/voice",
            "websocket": "/ws",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "hardware": {
            "connected": serial_manager is not None and serial_manager.is_connected,
            "port": settings.serial_port if serial_manager else None
        },
        "services": {
            "pc_monitoring": pc_monitor is not None and pc_monitor.running,
            "music": music_controller is not None,
            "calendar": calendar_service is not None,
            "voice_assistant": True
        }
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_ws_message(websocket, message)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


async def handle_ws_message(websocket: WebSocket, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")
    
    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})
    
    elif msg_type == "subscribe":
        channels = message.get("channels", [])
        for channel in channels:
            ws_manager.subscribe(websocket, channel)
    
    elif msg_type == "device_command":
        if serial_manager and serial_manager.is_connected:
            await serial_manager.send_command(message.get("command"), message.get("payload"))
    
    elif msg_type == "desktop_action":
        await handle_desktop_action(message.get("action"), message.get("payload"))
    
    else:
        logger.warning(f"Unknown WS message type: {msg_type}")


async def handle_desktop_action(action: str, payload: dict):
    """Handle desktop tool actions from WebSocket."""
    # This will be expanded with actual implementations
    logger.info(f"Desktop action: {action}, payload: {payload}")
    
    # Broadcast result to all subscribers
    await ws_manager.broadcast("desktop_response", {
        "action": action,
        "status": "received",
        "payload": payload
    })


async def ws_heartbeat_task():
    """Send periodic heartbeats to keep WebSocket connections alive."""
    while True:
        await asyncio.sleep(settings.ws_heartbeat_interval)
        await ws_manager.broadcast("heartbeat", {"timestamp": asyncio.get_event_loop().time()})


async def serial_read_task():
    """Continuously read from serial port and broadcast data."""
    if not serial_manager:
        return
    
    while True:
        try:
            if serial_manager.is_connected:
                line = await serial_manager.read_line()
                if line:
                    await ws_manager.broadcast("serial_data", {"data": line})
                    
                    # Try to parse as JSON for structured data
                    try:
                        data = json.loads(line)
                        await ws_manager.broadcast("sensor_data", data)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.error(f"Serial read error: {e}")
            await asyncio.sleep(1)


async def pc_metrics_broadcast_task():
    """Periodically broadcast PC metrics via WebSocket."""
    while True:
        try:
            if pc_monitor and pc_monitor.running:
                metrics = pc_monitor.get_metrics()
                await ws_manager.broadcast("pc_metrics", metrics)
        except Exception as e:
            logger.error(f"PC metrics broadcast error: {e}")
        await asyncio.sleep(5)  # Every 5 seconds


# Signal handling for graceful shutdown
def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    uvicorn.run(
        "desktop_bridge.main:app",
        host=settings.bridge_host,
        port=settings.bridge_port,
        reload=settings.bridge_debug,
        log_level="info"
    )