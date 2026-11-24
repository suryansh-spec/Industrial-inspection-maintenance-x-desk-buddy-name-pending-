"""
DeskBuddy Backend - Main Application Entry Point.

Unified backend for Industrial Inspection & Desk Companion.
Integrates: DeskMate + deskey-v2 + Hermes + StatNode + yt-music-companion
"""
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import companion, config, desktop_tools, device, gaming, plugins, system, vibration, voice
from app.core.config import LOGS_DIR, settings
from app.core.database import close_db, init_db
from app.core.event_bus import event_bus
from app.core.state_manager import state_manager
from app.core.plugin_loader import PluginLoader
from app.services import serial_manager as serial_state
from app.services.calendar import calendar_service
from app.services.companion import companion_service
from app.services.deskmate import create_deskbuddy_services, deskmate_service
from app.services.hardware_bridge import hardware_bridge
from app.services.music import music_controller
from app.services.notification_service import notification_service
from app.services.system_monitor import system_monitor
from app.services.voice import voice_assistant
from app.ws.manager import ws_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "deskbuddy_backend.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Background tasks started during application startup
_background_tasks: List[asyncio.Task] = []


async def _optional_startup(name: str, awaitable) -> bool:
    """Run an optional service startup step without aborting the app."""
    try:
        await awaitable
        return True
    except Exception as exc:  # pragma: no cover - depends on local environment
        logger.warning("%s failed to initialize: %s", name, exc)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - startup and shutdown."""
    logger.info("Starting DeskBuddy Backend...")

    # Database (non-fatal: the app can run in degraded mode without a DB)
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Database initialization failed: %s", exc)

    if settings.enable_pc_monitoring:
        await _optional_startup("System monitor", system_monitor.start())

    await _optional_startup("Notification service", notification_service.initialize())

    if settings.enable_music_control:
        await _optional_startup("Music controller", music_controller.initialize())

    if settings.enable_calendar:
        await _optional_startup("Calendar service", calendar_service.initialize())

    if settings.enable_voice_assistant:
        await _optional_startup("Voice assistant", voice_assistant.initialize())

    if settings.enable_hardware_bridge:
        try:
            if await hardware_bridge.connect():
                logger.info("Hardware bridge connected")
            else:
                logger.warning("Hardware bridge connection failed - running without hardware")
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning("Hardware bridge initialization failed: %s", exc)

    if settings.enable_desk_mate:
        create_deskbuddy_services()
        logger.info("DeskMate desktop companion initialized")

    if settings.enable_companion:
        await _optional_startup("Companion service", companion_service.start())
        try:
            from app.services.device_settings import store
            companion_service.activity.set_thresholds(store.get("sleep_thresholds") or {})
        except Exception:  # pragma: no cover - settings are optional
            logger.debug("Could not apply sleep thresholds", exc_info=True)

    # Initialize plugin system
    plugin_loader = PluginLoader(event_bus, state_manager, serial_state)
    app.state.plugin_loader = plugin_loader
    try:
        await plugin_loader.start_all()
        logger.info("Plugin system initialized: %d plugins", len(plugin_loader.plugins))
    except Exception as exc:
        logger.warning("Plugin system failed to initialize: %s", exc)

    # Background tasks
    _background_tasks.append(asyncio.create_task(ws_heartbeat_task()))
    _background_tasks.append(asyncio.create_task(serial_read_task()))
    if settings.enable_pc_monitoring:
        _background_tasks.append(asyncio.create_task(pc_metrics_broadcast_task()))
    if settings.enable_companion:
        _background_tasks.append(asyncio.create_task(companion_state_task()))
        if settings.enable_music_control:
            _background_tasks.append(asyncio.create_task(lyrics_refresh_task()))
        # Gaming mode tick (every 5 seconds)
        _background_tasks.append(asyncio.create_task(gaming_tick_task()))
        # User-authored notification rules (every 5 seconds)
        _background_tasks.append(asyncio.create_task(notification_rules_task()))

    logger.info("DeskBuddy Backend started successfully")

    try:
        yield
    finally:
        logger.info("Shutting down DeskBuddy Backend...")

        for task in _background_tasks:
            task.cancel()
        for task in _background_tasks:
            with suppress(asyncio.CancelledError):
                await task
        _background_tasks.clear()

        manager = serial_state.get_serial_manager()
        if manager:
            with suppress(Exception):
                await manager.disconnect()

        with suppress(Exception):
            await system_monitor.stop()
        with suppress(Exception):
            await music_controller.cleanup()
        with suppress(Exception):
            await calendar_service.cleanup()
        with suppress(Exception):
            await voice_assistant.cleanup()
        with suppress(Exception):
            await hardware_bridge.disconnect()
        with suppress(Exception):
            await companion_service.stop()
        with suppress(Exception):
            from app.services.lyrics import lyrics_service

            await lyrics_service.close()

        with suppress(Exception):
            await close_db()

        logger.info("DeskBuddy Backend stopped")


app = FastAPI(
    title="DeskBuddy Backend",
    description="Unified backend for Industrial Inspection & Desk Companion",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(vibration.router, prefix=settings.api_prefix)
app.include_router(device.router, prefix=settings.api_prefix)
app.include_router(desktop_tools.router, prefix=settings.api_prefix)
app.include_router(voice.router, prefix=settings.api_prefix)
app.include_router(companion.router, prefix=settings.api_prefix)
app.include_router(gaming.router, prefix=settings.api_prefix)
app.include_router(config.router, prefix=settings.api_prefix)
app.include_router(plugins.router, prefix=settings.api_prefix)

# Serve web control panel
import os
_web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.isdir(_web_dir):
    app.mount("/panel", StaticFiles(directory=_web_dir, html=True), name="panel")

@app.get("/")
async def root():
    return FileResponse(os.path.join(_web_dir, "index.html"))


# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "system_monitor": bool(getattr(system_monitor, "running", False)),
            "hardware_bridge": (
                hardware_bridge.state.value
                if hasattr(hardware_bridge, "state") and hasattr(hardware_bridge.state, "value")
                else "unknown"
            ),
            "websocket_clients": ws_manager.get_connection_count(),
        },
    }


# (duplicate root route removed - the FileResponse handler above serves index.html)


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            await handle_ws_message(websocket, message)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
    finally:
        ws_manager.disconnect(websocket)


async def handle_ws_message(websocket: WebSocket, message: dict):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    elif msg_type == "subscribe":
        for channel in message.get("channels", []):
            ws_manager.subscribe(websocket, channel)

    elif msg_type == "unsubscribe":
        for channel in message.get("channels", []):
            ws_manager.unsubscribe(websocket, channel)

    elif msg_type == "device_command":
        manager = serial_state.get_serial_manager()
        if manager and manager.is_connected:
            await manager.send_command(message.get("command"), message.get("payload"))

    elif msg_type == "voice_query":
        result = await voice_assistant.process_query(
            message.get("text", ""), message.get("context")
        )
        await websocket.send_json({"type": "voice_response", **result})

    elif msg_type == "notification":
        notification = deskmate_service.add_notification(
            title=message.get("title", "Notification"),
            message=message.get("message", ""),
            type=message.get("level", "info"),
            actions=message.get("actions"),
        )
        await ws_manager.broadcast("notifications", notification.to_dict())
        await companion_service.push_notification(
            notification.title,
            notification.message,
            priority=int(message.get("priority", 1) or 1),
            notification_id=notification.id,
        )

    else:
        await websocket.send_json(
            {"type": "error", "message": f"Unknown message type: {msg_type}"}
        )


async def ws_heartbeat_task():
    """Send periodic heartbeats to keep WebSocket connections alive."""
    interval = max(5, int(settings.ws_heartbeat_interval))
    while True:
        await asyncio.sleep(interval)
        await ws_manager.broadcast(
            "heartbeat", {"timestamp": datetime.now(timezone.utc).isoformat()}
        )


async def serial_read_task():
    """Read device messages, update telemetry and fan out events."""
    while True:
        manager = serial_state.get_serial_manager()
        if manager and manager.is_connected:
            try:
                line = await manager.read_line()
                if line:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        await ws_manager.broadcast("serial_raw", {"data": line})
                    else:
                        await ws_manager.broadcast("serial_data", payload)

                        events = await companion_service.handle_device_message(payload)
                        for event in events:
                            await ws_manager.broadcast(event["channel"], event["data"])
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.error("Serial read error: %s", exc)
        await asyncio.sleep(0.1)


async def lyrics_refresh_task():
    """Resolve lyrics for the current track without blocking the state push."""
    while True:
        try:
            await companion_service.refresh_lyrics()
        except Exception:
            logger.debug("Lyrics refresh failed", exc_info=True)
        await asyncio.sleep(0.5)


async def gaming_tick_task():
    """Gaming mode: detect games, track sessions, check alerts."""
    while True:
        try:
            from app.services.gaming import gaming_service
            await gaming_service.tick()
        except Exception:
            logger.debug("Gaming tick failed", exc_info=True)
        await asyncio.sleep(5.0)


async def notification_rules_task():
    """Evaluate user-authored IF/THEN notification rules."""
    while True:
        try:
            from app.services.rule_engine import rule_engine
            await rule_engine.tick()
        except Exception:
            logger.debug("Notification rule tick failed", exc_info=True)
        await asyncio.sleep(5.0)


async def companion_state_task():
    """Push the companion state to WebSocket clients and the device."""
    interval = max(0.5, float(settings.companion_push_interval))
    while True:
        try:
            # Refresh lyrics + cover art on every tick so new tracks are
            # detected even when the device hasn't sent a music message.
            # Cache keys make this a no-op when nothing changed.
            await companion_service.refresh_lyrics()
            summary = companion_service.get_summary()
            await ws_manager.broadcast("deskbuddy_state", summary)
            await ws_manager.broadcast(
                "activity",
                {
                    key: summary.get(key)
                    for key in (
                        "activity",
                        "expression",
                        "sleep_stage",
                        "app",
                        "window",
                        "idle_seconds",
                        "description",
                    )
                },
            )

            state = companion_service.get_device_state(summary=summary)
            if hardware_bridge.is_connected:
                await hardware_bridge.send_command(
                    "deskbuddy_state",
                    state,
                )
        except Exception:
            logger.exception("Companion state push failed")

        await asyncio.sleep(interval)


async def pc_metrics_broadcast_task():
    """Broadcast PC metrics periodically."""
    while True:
        await asyncio.sleep(5)
        if getattr(system_monitor, "running", False):
            metrics = system_monitor.get_metrics()
            if metrics:
                await ws_manager.broadcast("pc_metrics", metrics)


def main():
    """Run the application."""
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
