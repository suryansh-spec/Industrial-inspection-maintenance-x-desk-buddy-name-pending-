"""Persistent panel/device settings.

The web panel edits a handful of small, sparse documents (expression mapping,
button map, notification rules, TFT theme, display font + wallpaper). They are
kept in one JSON file so they survive restarts without a schema migration, and
per-user settings are intentionally *not* committed (``data/`` is gitignored).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_FILE = _DATA_DIR / "device_settings.json"
_WALLPAPER_PNG = _DATA_DIR / "wallpaper.png"
_WALLPAPER_RAW = _DATA_DIR / "wallpaper.bin"

# --- Firmware contract -------------------------------------------------------
# Keep these lists in the exact order the sketch expects: the numeric button
# map is transmitted as a flat array of indices into BUTTON_ACTIONS.
BUTTONS = ["mode", "voice", "up", "down", "select"]
PAGES = ["home", "music", "lyrics", "pc", "env", "notifications", "pomodoro"]
BUTTON_ACTIONS = [
    "next_page",     # 0
    "prev_page",     # 1
    "play_pause",    # 2
    "volume_up",     # 3
    "volume_down",   # 4
    "toggle_mode",   # 5
    "voice_request", # 6
    "none",          # 7
    "default",       # 8  -> fall back to the firmware's contextual behaviour
]

ACTIVITIES = ["idle", "coding", "browsing", "music", "gaming", "watching", "typing", "thinking"]
EXPRESSIONS = ["relaxed", "happy", "sad", "angry", "sleepy", "thinking", "curious",
               "excited", "surprised", "confused", "laughing", "music", "typing",
               "coding", "browsing", "gaming", "watching", "sleeping", "deep_sleep",
               "autonomous"]

WALLPAPER_W = 128
WALLPAPER_H = 160
WALLPAPER_CHUNK = 1536  # raw bytes per serial chunk (2048 base64 chars)

METRICS: List[Dict[str, str]] = [
    {"id": "cpu", "label": "CPU %", "field": "cpu_percent"},
    {"id": "mem", "label": "RAM %", "field": "memory_percent"},
    {"id": "gpu", "label": "GPU %", "field": "gpu_percent"},
    {"id": "gpu_temp", "label": "GPU temp °C", "field": "gpu_temp_c"},
    {"id": "cpu_temp", "label": "CPU temp °C", "field": "cpu_temp_c"},
    {"id": "disk", "label": "Disk %", "field": "disk_percent"},
    {"id": "env_temp", "label": "Room temp °C", "field": "temperature", "source": "environment"},
    {"id": "env_hum", "label": "Humidity %", "field": "humidity", "source": "environment"},
    {"id": "battery", "label": "Battery %", "field": "battery_percent", "source": "device"},
]


def _default_button_map() -> List[List[int]]:
    default = BUTTON_ACTIONS.index("default")
    per_button = {
        "mode": BUTTON_ACTIONS.index("toggle_mode"),
        "voice": BUTTON_ACTIONS.index("voice_request"),
        "up": BUTTON_ACTIONS.index("prev_page"),
        "down": BUTTON_ACTIONS.index("next_page"),
        "select": default,
    }
    return [[per_button[b] for _ in PAGES] for b in BUTTONS]


DEFAULTS: Dict[str, Any] = {
    "expressions": {a: a for a in ACTIVITIES},
    "button_map": _default_button_map(),
    "notification_rules": [],
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
    "display": {
        "font_face": "pixel",          # pixel (Org_01) | compact (TomThumb)
        "wallpaper_opacity": 150,      # 0..255 scrim toward the theme background
    },
    "sleep_thresholds": {
        "sleepy_seconds": 30,
        "sleep_seconds": 120,
        "deep_sleep_seconds": 300,
    },
}


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _merge(base.get(k), v) if k in base else v
        return out
    return override


class SettingsStore:
    """Thread-safe JSON document with atomic writes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = json.loads(json.dumps(DEFAULTS))
        self._load()

    # -- persistence --------------------------------------------------------
    def _load(self) -> None:
        try:
            if _FILE.exists():
                raw = json.loads(_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = _merge(self._data, raw)
                    logger.info("Loaded device settings from %s", _FILE)
        except Exception:  # pragma: no cover - corrupt file should not be fatal
            logger.warning("Could not read %s, using defaults", _FILE, exc_info=True)

    def _save(self) -> None:
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(_FILE)
        except Exception:  # pragma: no cover - disk dependent
            logger.warning("Could not persist device settings", exc_info=True)

    # -- access -------------------------------------------------------------
    def get(self, section: str) -> Any:
        with self._lock:
            value = self._data.get(section, DEFAULTS.get(section))
            return json.loads(json.dumps(value))

    def update(self, section: str, values: Dict[str, Any]) -> Any:
        with self._lock:
            current = self._data.setdefault(section, {})
            if isinstance(current, dict):
                current.update(values or {})
            else:
                self._data[section] = values
            self._save()
            return self.get(section)

    def replace(self, section: str, value: Any) -> Any:
        with self._lock:
            self._data[section] = value
            self._save()
            return self.get(section)

    # -- convenience --------------------------------------------------------
    def button_map(self) -> List[List[int]]:
        value = self.get("button_map")
        if not isinstance(value, list) or len(value) != len(BUTTONS):
            return _default_button_map()
        return value

    def set_button_map(self, rows: List[List[int]]) -> List[List[int]]:
        clean: List[List[int]] = []
        for b in range(len(BUTTONS)):
            row = rows[b] if b < len(rows) and isinstance(rows[b], list) else []
            clean.append([
                int(row[p]) if p < len(row) and 0 <= int(row[p]) < len(BUTTON_ACTIONS) else 0
                for p in range(len(PAGES))
            ])
        return self.replace("button_map", clean)

    def flat_button_map(self) -> List[int]:
        return [int(v) for row in self.button_map() for v in row]

    def expressions(self) -> Dict[str, str]:
        value = self.get("expressions")
        return value if isinstance(value, dict) else {a: a for a in ACTIVITIES}

    def rules(self) -> List[Dict[str, Any]]:
        value = self.get("notification_rules")
        return value if isinstance(value, list) else []


store = SettingsStore()


# --- Wallpaper ---------------------------------------------------------------
def has_wallpaper() -> bool:
    return _WALLPAPER_RAW.exists()


def wallpaper_png_bytes() -> Optional[bytes]:
    try:
        return _WALLPAPER_PNG.read_bytes() if _WALLPAPER_PNG.exists() else None
    except Exception:  # pragma: no cover
        return None


def wallpaper_raw_bytes() -> Optional[bytes]:
    try:
        return _WALLPAPER_RAW.read_bytes() if _WALLPAPER_RAW.exists() else None
    except Exception:  # pragma: no cover
        return None


def process_wallpaper(image_bytes: bytes) -> bytes:
    """Resize an uploaded image to 128x160 and store preview + raw RGB565."""
    from io import BytesIO

    from PIL import Image, ImageOps

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.fit(img, (WALLPAPER_W, WALLPAPER_H), Image.LANCZOS)
    img.save(_WALLPAPER_PNG, format="PNG")

    raw = bytearray(WALLPAPER_W * WALLPAPER_H * 2)
    i = 0
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        raw[i] = v & 0xFF        # little-endian, matches the device buffer
        raw[i + 1] = (v >> 8) & 0xFF
        i += 2
    _WALLPAPER_RAW.write_bytes(bytes(raw))
    return bytes(raw)


def clear_wallpaper() -> None:
    for path in (_WALLPAPER_RAW, _WALLPAPER_PNG):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception:  # pragma: no cover
            logger.warning("Could not delete %s", path, exc_info=True)


# --- Device push -------------------------------------------------------------
async def push_wallpaper(manager, chunk_delay: float = 0.05) -> bool:
    if not manager or not manager.is_connected:
        return False
    raw = wallpaper_raw_bytes()
    display = store.get("display") or {}
    opacity = int(display.get("wallpaper_opacity", 150))
    if not raw:
        await manager.send_command("wallpaper_clear", {})
        return True

    total = len(raw)
    await manager.send_command("wallpaper_begin", {
        "w": WALLPAPER_W, "h": WALLPAPER_H, "total": total, "opacity": opacity,
    })
    for seq, off in enumerate(range(0, total, WALLPAPER_CHUNK)):
        chunk = raw[off:off + WALLPAPER_CHUNK]
        ok = await manager.send_command("wallpaper_chunk", {
            "seq": seq,
            "data": base64.b64encode(chunk).decode("ascii"),
        })
        if not ok:
            logger.warning("Wallpaper chunk %d failed", seq)
            return False
        # The sketch renders at ~25 fps and reads serial once per loop, so pace
        # the transfer instead of flooding its 16 kB RX buffer.
        await asyncio.sleep(chunk_delay)
    await manager.send_command("wallpaper_end", {"opacity": opacity})
    return True


async def push_display(manager) -> None:
    if not manager or not manager.is_connected:
        return
    display = store.get("display") or {}
    await manager.send_command("set_font", {
        "face": display.get("font_face", "pixel"),
        "opacity": int(display.get("wallpaper_opacity", 150)),
    })


async def push_all(manager) -> None:
    """Re-apply every device-owned setting (called after (re)connecting)."""
    if not manager or not manager.is_connected:
        return
    try:
        await manager.send_command("set_theme", store.get("device_theme"))
        await manager.send_command("set_buttons", {"map": store.flat_button_map()})
        await push_display(manager)
        await push_wallpaper(manager)
    except Exception:  # pragma: no cover - hardware dependent
        logger.warning("Could not push device settings", exc_info=True)
