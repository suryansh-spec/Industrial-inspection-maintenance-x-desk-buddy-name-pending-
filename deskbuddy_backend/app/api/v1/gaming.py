"""
Gaming Mode API endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from app.services.gaming import gaming_service

router = APIRouter(prefix="/gaming", tags=["gaming"])


class GamingConfig(BaseModel):
    enabled: bool = False
    auto_detect: bool = True
    gpu_threshold: float = 30.0
    cpu_threshold: float = 25.0
    sustained_seconds: int = 10
    fullscreen_detection: bool = True
    gpu_temp_threshold: float = 80.0
    cpu_temp_threshold: float = 85.0
    vram_threshold: float = 90.0
    game_library: List[str] = []


class GameLibraryUpdate(BaseModel):
    games: List[str]


class AlertConfig(BaseModel):
    gpu_temp_threshold: Optional[float] = None
    cpu_temp_threshold: Optional[float] = None
    vram_threshold: Optional[float] = None
    cpu_usage_threshold: Optional[float] = None
    cooldown_seconds: Optional[int] = None


@router.get("/status")
async def get_gaming_status():
    """Get current gaming mode status."""
    return gaming_service.get_status()


@router.post("/config")
async def update_gaming_config(config: GamingConfig):
    """Update gaming mode configuration."""
    gaming_service.configure(config.model_dump())
    return gaming_service.get_status()


@router.post("/enable")
async def enable_gaming():
    """Enable gaming mode."""
    gaming_service.enabled = True
    return {"status": "enabled"}


@router.post("/disable")
async def disable_gaming():
    """Disable gaming mode."""
    gaming_service.enabled = False
    gaming_service.current_session = None
    return {"status": "disabled"}


@router.get("/sessions")
async def list_gaming_sessions():
    """List gaming sessions (current + recent)."""
    sessions = []
    if gaming_service.current_session:
        sessions.append(gaming_service.current_session)
    return {"sessions": sessions, "count": len(sessions)}


@router.post("/library/add")
async def add_game(update: GameLibraryUpdate):
    """Add games to the library."""
    gaming_service.game_library.update(g.lower() for g in update.games)
    return {"status": "added", "library": sorted(gaming_service.game_library)}


@router.post("/library/remove")
async def remove_game(update: GameLibraryUpdate):
    """Remove games from the library."""
    gaming_service.game_library -= set(g.lower() for g in update.games)
    return {"status": "removed", "library": sorted(gaming_service.game_library)}


@router.put("/alerts")
async def update_alerts(config: AlertConfig):
    """Update alert thresholds."""
    if config.gpu_temp_threshold is not None:
        gaming_service.gpu_temp_threshold = config.gpu_temp_threshold
    if config.cpu_temp_threshold is not None:
        gaming_service.cpu_temp_threshold = config.cpu_temp_threshold
    if config.vram_threshold is not None:
        gaming_service.vram_threshold = config.vram_threshold
    if config.cpu_usage_threshold is not None:
        gaming_service.cpu_usage_threshold = config.cpu_usage_threshold
    if config.cooldown_seconds is not None:
        gaming_service._alert_cooldown_seconds = config.cooldown_seconds
    return gaming_service.get_status()["config"]


@router.get("/alerts")
async def get_alerts():
    """Get recent gaming alerts."""
    return {"alerts": gaming_service._alerts[-20:]}