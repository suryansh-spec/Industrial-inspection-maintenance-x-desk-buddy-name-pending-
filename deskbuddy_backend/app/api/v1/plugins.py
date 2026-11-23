"""Plugin management API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _get_loader(app):
    loader = getattr(app.state, "plugin_loader", None)
    if not loader:
        raise HTTPException(status_code=503, detail="Plugin system not initialized")
    return loader


@router.get("/")
async def list_plugins():
    from fastapi import Request
    # Get loader from app state
    from app.main import app
    loader = _get_loader(app)
    return {"plugins": loader.list_plugins()}


@router.post("/{plugin_id}/start")
async def start_plugin(plugin_id: str):
    from app.main import app
    loader = _get_loader(app)
    if await loader.start_plugin(plugin_id):
        return {"status": "started", "plugin": plugin_id}
    raise HTTPException(status_code=400, detail=f"Failed to start {plugin_id}")


@router.post("/{plugin_id}/stop")
async def stop_plugin(plugin_id: str):
    from app.main import app
    loader = _get_loader(app)
    if await loader.stop_plugin(plugin_id):
        return {"status": "stopped", "plugin": plugin_id}
    raise HTTPException(status_code=400, detail=f"Failed to stop {plugin_id}")


@router.post("/{plugin_id}/reload")
async def reload_plugin(plugin_id: str):
    from app.main import app
    loader = _get_loader(app)
    await loader.unload_plugin(plugin_id)
    if await loader.load_plugin(plugin_id):
        if await loader.start_plugin(plugin_id):
            return {"status": "reloaded", "plugin": plugin_id}
    raise HTTPException(status_code=400, detail=f"Failed to reload {plugin_id}")


@router.get("/events")
async def get_recent_events(limit: int = 50, event: str = None):
    from app.core.event_bus import event_bus
    return {"events": event_bus.get_recent_events(event, limit)}