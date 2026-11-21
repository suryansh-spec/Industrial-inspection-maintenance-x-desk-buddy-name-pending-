"""Configuration API endpoints for the web control panel.

Everything editable here is persisted through
:mod:`app.services.device_settings` and, where the hardware cares, pushed to the
ESP32 immediately. ``POST /config/push`` re-applies everything after a flash or
reconnect.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.services import device_settings as ds
from app.services.activity import Expression
from app.services.device_settings import BUTTON_ACTIONS, BUTTONS, PAGES, store
from app.services.rule_engine import metric_values, new_rule, normalize_rule, rule_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])

# Panel-only (browser) appearance. Kept separate from the TFT theme.
_panel_theme: Dict[str, Any] = {
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
}

_settings: Dict[str, Any] = {
    "serial_port": "COM6",
    "baud_rate": 112000,
    "pc_metrics_interval_ms": 1000,
    "sensor_data_interval_ms": 2000,
    "state_push_interval_ms": 500,
    "tft_brightness": 220,
    "oled_contrast": 255,
    "lyrics_enabled": True,
    "lyrics_sync_offset_ms": 500,
}


class ExpressionMapping(BaseModel):
    activity: str
    expression: str


class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]


async def _manager():
    from app.services import serial_manager as serial_state
    manager = serial_state.get_serial_manager()
    return manager if manager and manager.is_connected else None


async def _push(command: str, payload: Dict[str, Any]) -> None:
    manager = await _manager()
    if manager:
        try:
            await manager.send_command(command, payload)
        except Exception:  # pragma: no cover - hardware dependent
            logger.debug("push %s failed", command, exc_info=True)


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
@router.get("/expressions")
async def get_expressions():
    mappings = store.expressions()
    return {
        "mappings": [{"activity": k, "expression": v} for k, v in mappings.items()],
        "activities": ds.ACTIVITIES,
        "expressions": [e.value for e in Expression],
    }


@router.put("/expressions")
async def update_expressions(payload: Any = Body(...)):
    """Accept either a list of {activity, expression} or {"mappings": [...]}."""
    items: List[Any] = []
    if isinstance(payload, dict):
        items = payload.get("mappings") or []
    elif isinstance(payload, list):
        items = payload
    updated = store.expressions()
    for item in items:
        if isinstance(item, dict):
            activity = str(item.get("activity") or "").strip()
            expression = str(item.get("expression") or "").strip()
            if activity:
                updated[activity] = expression
    store.replace("expressions", updated)
    return {"status": "updated", "mappings": [{"activity": k, "expression": v} for k, v in updated.items()]}


# ---------------------------------------------------------------------------
# Panel settings (browser)
# ---------------------------------------------------------------------------
@router.get("/settings")
async def get_settings():
    return _settings


@router.put("/settings")
async def update_settings(update: SettingsUpdate):
    _settings.update(update.settings or {})
    return {"status": "updated", "settings": _settings}


# ---------------------------------------------------------------------------
# Button mappings
# ---------------------------------------------------------------------------
def _buttons_payload() -> Dict[str, Any]:
    return {
        "buttons": BUTTONS,
        "pages": PAGES,
        "actions": BUTTON_ACTIONS,
        "map": store.button_map(),
        "mappings": {
            BUTTONS[b]: {PAGES[p]: BUTTON_ACTIONS[store.button_map()[b][p]] for p in range(len(PAGES))}
            for b in range(len(BUTTONS))
        },
    }


@router.get("/buttons")
async def get_button_mappings():
    return _buttons_payload()


@router.put("/buttons")
async def update_button_mappings(payload: Any = Body(...)):
    rows: Optional[List[List[int]]] = None
    if isinstance(payload, dict):
        if isinstance(payload.get("map"), list):
            rows = payload["map"]
        elif isinstance(payload.get("mappings"), dict):
            by_name = payload["mappings"]
            rows = []
            for b in BUTTONS:
                row = by_name.get(b) or {}
                rows.append([
                    BUTTON_ACTIONS.index(row.get(p)) if row.get(p) in BUTTON_ACTIONS else 0
                    for p in PAGES
                ])
    elif isinstance(payload, list):
        rows = payload
    if rows is None:
        raise HTTPException(status_code=400, detail="Expected {'map': [[...]]} or a row array")

    try:
        store.set_button_map(rows)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid button map: {exc}") from exc

    await _push("set_buttons", {"map": store.flat_button_map()})
    return {"status": "updated", **_buttons_payload()}


# ---------------------------------------------------------------------------
# Device (TFT) theme
# ---------------------------------------------------------------------------
@router.get("/device-theme")
async def get_device_theme():
    return store.get("device_theme")


@router.put("/device-theme")
async def update_device_theme(theme: Dict[str, Any]):
    updated = store.update("device_theme", theme or {})
    await _push("set_theme", updated)
    return {"status": "updated", "theme": updated}


@router.get("/theme")
async def get_theme():
    return _panel_theme


@router.put("/theme")
async def update_theme(theme: Dict[str, Any]):
    _panel_theme.update(theme or {})
    return {"status": "updated", "theme": _panel_theme}


@router.get("/theme/presets")
async def get_theme_presets():
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


# ---------------------------------------------------------------------------
# Display: font face + wallpaper
# ---------------------------------------------------------------------------
@router.get("/display")
async def get_display():
    display = store.get("display") or {}
    return {
        "font_face": display.get("font_face", "pixel"),
        "wallpaper_opacity": int(display.get("wallpaper_opacity", 150)),
        "wallpaper": ds.has_wallpaper(),
        "fonts": [
            {"id": "pixel", "label": "Pixel (Org_01)"},
            {"id": "compact", "label": "Compact (TomThumb)"},
        ],
    }


@router.put("/display")
async def update_display(values: Dict[str, Any]):
    allowed = {k: v for k, v in (values or {}).items() if k in ("font_face", "wallpaper_opacity")}
    if "font_face" in allowed and allowed["font_face"] not in ("pixel", "compact"):
        raise HTTPException(status_code=400, detail="font_face must be 'pixel' or 'compact'")
    if "wallpaper_opacity" in allowed:
        try:
            allowed["wallpaper_opacity"] = max(0, min(255, int(allowed["wallpaper_opacity"])))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="wallpaper_opacity must be 0..255")
    updated = store.update("display", allowed)
    await ds.push_display(await _manager())
    if "wallpaper_opacity" in allowed and ds.has_wallpaper():
        await ds.push_wallpaper(await _manager())
    return {"status": "updated", "display": updated, "wallpaper": ds.has_wallpaper()}


def _decode_data_url(data: str) -> bytes:
    if not data:
        raise HTTPException(status_code=400, detail="Missing image data")
    if data.startswith("data:"):
        try:
            data = data.split(",", 1)[1]
        except IndexError:
            raise HTTPException(status_code=400, detail="Malformed data URL")
    try:
        raw = base64.b64decode(data, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Image is not valid base64")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 12 MB)")
    return raw


@router.post("/wallpaper")
async def upload_wallpaper(payload: Dict[str, Any]):
    raw = _decode_data_url(str((payload or {}).get("image") or ""))
    try:
        await asyncio.to_thread(ds.process_wallpaper, raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}") from exc
    await ds.push_wallpaper(await _manager())
    return {"status": "uploaded", "wallpaper": True, "width": ds.WALLPAPER_W, "height": ds.WALLPAPER_H}


@router.get("/wallpaper")
async def get_wallpaper():
    png = ds.wallpaper_png_bytes()
    if not png:
        return {"present": False, "data": None}
    return {"present": True, "data": base64.b64encode(png).decode("ascii")}


@router.delete("/wallpaper")
async def delete_wallpaper():
    ds.clear_wallpaper()
    await _push("wallpaper_clear", {})
    return {"status": "cleared", "wallpaper": False}


# ---------------------------------------------------------------------------
# Notification rules
# ---------------------------------------------------------------------------
def _rules() -> List[Dict[str, Any]]:
    return [normalize_rule(r) for r in store.rules()]


@router.get("/notification-rules")
async def get_notification_rules():
    return {"rules": _rules(), "metrics": ds.METRICS, "operators": list((">", ">=", "<", "<=", "==", "!="))}


@router.post("/notification-rules")
async def create_notification_rule(values: Dict[str, Any]):
    rule = normalize_rule(new_rule(values))
    rules = _rules()
    rules.append(rule)
    store.replace("notification_rules", rules)
    return {"status": "created", "rule": rule, "rules": rules}


@router.put("/notification-rules/{rule_id}")
async def update_notification_rule(rule_id: str, values: Dict[str, Any]):
    rules = _rules()
    for index, rule in enumerate(rules):
        if rule["id"] == rule_id:
            merged = dict(rule)
            merged.update(values or {})
            merged["id"] = rule_id
            rules[index] = normalize_rule(merged)
            store.replace("notification_rules", rules)
            return {"status": "updated", "rule": rules[index], "rules": rules}
    raise HTTPException(status_code=404, detail="Rule not found")


@router.delete("/notification-rules/{rule_id}")
async def delete_notification_rule(rule_id: str):
    rules = [r for r in _rules() if r["id"] != rule_id]
    store.replace("notification_rules", rules)
    return {"status": "deleted", "rules": rules}


@router.post("/notification-rules/{rule_id}/test")
async def test_notification_rule(rule_id: str):
    for rule in _rules():
        if rule["id"] == rule_id:
            values = metric_values()
            value = values.get(rule["metric"], rule["threshold"] + 1)
            await rule_engine.fire(rule, value)
            return {"status": "fired", "rule": rule, "value": value}
    raise HTTPException(status_code=404, detail="Rule not found")


# ---------------------------------------------------------------------------
# Apply everything to the device
# ---------------------------------------------------------------------------
@router.post("/push")
async def push_all_settings():
    manager = await _manager()
    if not manager:
        raise HTTPException(status_code=409, detail="Device is not connected")
    await ds.push_all(manager)
    return {"status": "pushed", "buttons": store.flat_button_map(), "theme": store.get("device_theme")}
