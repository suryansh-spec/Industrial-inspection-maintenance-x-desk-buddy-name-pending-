"""
Configuration API endpoints for the web control panel.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter(prefix="/config", tags=["config"])

# In-memory config store (will be persisted to DB later)
_config_store: Dict[str, Any] = {
    "expressions": {
        "idle": "relaxed",
        "coding": "coding",
        "browsing": "browsing",
        "music": "music",
        "gaming": "gaming",
        "watching": "watching",
        "typing": "typing",
        "thinking": "thinking",
    },
    "sleep_thresholds": {
        "sleepy_seconds": 30,
        "sleep_seconds": 120,
        "deep_sleep_seconds": 300,
    },
    "button_mappings": {},
    "theme": {
        "preset": "dark",
        "accent_color": "#06b6d4",
        "background": "#0f172a",
        "card_bg": "#1e293b",
        "text_color": "#e2e8f0",
        "text_secondary": "#94a3b8",
        "border_color": "#334155",
        "success_color": "#22c55e",
        "warning_color": "#f59e0b",
        "danger_color": "#ef4444",
        "wallpaper": "",
        "wallpaper_opacity": 0.3,
        "font_size": "medium",
        "card_style": "solid",
        "border_radius": 12,
        "sidebar_position": "left",
    },
    "device_theme": {
        "bg_color": "#000000",
        "text_color": "#FFFFFF",
        "accent_color": "#07FF",
        "secondary_color": "#8410",
        "warning_color": "#FD20",
        "success_color": "#07E0",
        "danger_color": "#F800",
        "header_bg": "#0010",
        "header_text": "#FFFFFF",
        "title_size": 2,
        "body_size": 1,
        "big_size": 3,
        "timer_size": 4,
    },
    "settings": {
        "serial_port": "COM6",
        "baud_rate": 115200,
        "pc_metrics_interval_ms": 1000,
        "sensor_data_interval_ms": 2000,
        "state_push_interval_ms": 500,
        "tft_brightness": 220,
        "oled_contrast": 255,
        "lyrics_enabled": True,
        "lyrics_sync_offset_ms": 500,
    },
}


class ExpressionMapping(BaseModel):
    activity: str
    expression: str


class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]


@router.get("/expressions")
async def get_expressions():
    """Get expression mappings."""
    return {"mappings": [{"activity": k, "expression": v} for k, v in _config_store["expressions"].items()]}


@router.put("/expressions")
async def update_expressions(mappings: List[ExpressionMapping]):
    """Update expression mappings."""
    for m in mappings:
        _config_store["expressions"][m.activity] = m.expression
    return {"status": "updated", "mappings": _config_store["expressions"]}


@router.get("/settings")
async def get_settings():
    """Get all settings."""
    return _config_store["settings"]


@router.put("/settings")
async def update_settings(update: SettingsUpdate):
    """Update settings."""
    _config_store["settings"].update(update.settings)
    return {"status": "updated", "settings": _config_store["settings"]}


@router.get("/buttons")
async def get_button_mappings():
    """Get button mappings."""
    return {"mappings": _config_store["button_mappings"]}


@router.put("/buttons")
async def update_button_mappings(mappings: Dict[str, Any]):
    """Update button mappings."""
    _config_store["button_mappings"] = mappings
    return {"status": "updated"}


@router.get("/device-theme")
async def get_device_theme():
    """Get device display theme."""
    return _config_store["device_theme"]


@router.put("/device-theme")
async def update_device_theme(theme: Dict[str, Any]):
    """Update device display theme and push to device."""
    _config_store["device_theme"].update(theme)
    # Push to device via serial
    try:
        from app.services import serial_manager as serial_state
        manager = serial_state.get_serial_manager()
        if manager and manager.is_connected:
            await manager.send_command("set_theme", _config_store["device_theme"])
    except Exception:
        pass
    return {"status": "updated", "theme": _config_store["device_theme"]}


@router.get("/theme")
async def get_theme():
    """Get current theme settings."""
    return _config_store["theme"]


@router.put("/theme")
async def update_theme(theme: Dict[str, Any]):
    """Update theme settings."""
    _config_store["theme"].update(theme)
    return {"status": "updated", "theme": _config_store["theme"]}


@router.get("/theme/presets")
async def get_theme_presets():
    """Get available theme presets."""
    return {
        "presets": [
            {"id": "dark", "name": "Dark", "accent": "#06b6d4", "bg": "#0f172a", "card": "#1e293b", "text": "#e2e8f0"},
            {"id": "light", "name": "Light", "accent": "#0891b2", "bg": "#f8fafc", "card": "#ffffff", "text": "#1e293b"},
            {"id": "cyberpunk", "name": "Cyberpunk", "accent": "#f0abfc", "bg": "#0a0a0f", "card": "#1a1a2e", "text": "#e0e0ff"},
            {"id": "ocean", "name": "Ocean", "accent": "#38bdf8", "bg": "#0c1929", "card": "#132f4c", "text": "#b3d9ff"},
            {"id": "forest", "name": "Forest", "accent": "#4ade80", "bg": "#0a1a0f", "card": "#1a2e1a", "text": "#d4f0d4"},
            {"id": "sunset", "name": "Sunset", "accent": "#fb923c", "bg": "#1a0a0a", "card": "#2e1a1a", "text": "#ffe4d4"},
            {"id": "midnight", "name": "Midnight", "accent": "#818cf8", "bg": "#0a0a1a", "card": "#1a1a3e", "text": "#d4d4ff"},
            {"id": "rose", "name": "Rose", "accent": "#f472b6", "bg": "#1a0a14", "card": "#2e1a24", "text": "#ffd4e4"},
        ]
    }