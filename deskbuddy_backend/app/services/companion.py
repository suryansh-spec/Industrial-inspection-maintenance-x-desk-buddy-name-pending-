"""
DeskBuddy companion orchestration.

Combines three layers:

* :mod:`app.services.activity` - what the PC user is doing (deskey-v2).
* PC / media / productivity services - StatNode, yt-music-companion, DeskMate.
* device telemetry - the ESP32's sensors, battery, page and heartbeat.

The result is a compact state that is broadcast over WebSocket and pushed to
the Arduino firmware over serial.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.activity import ActivityService, activity_service

logger = logging.getLogger(__name__)


def _clean(value: Any, max_length: int = 64) -> str:
    """Make a string safe and short enough for a serial JSON line."""

    text = str(value or "")
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return text[:max_length]


@dataclass
class DeviceTelemetry:
    """Latest telemetry reported by the ESP32."""

    last_seen: Optional[float] = None
    last_heartbeat: Optional[float] = None
    sensors: Dict[str, float] = field(default_factory=dict)
    accel: Dict[str, float] = field(default_factory=dict)
    battery: float = 0.0
    battery_pct: float = -1.0
    battery_charging: int = -1
    mic_level: int = -1
    page: str = "home"
    mode: str = "desk_buddy"
    expression: str = ""
    firmware: str = ""
    last_gesture: str = ""
    last_gesture_at: Optional[datetime] = None


class CompanionService:
    """Owns device telemetry and produces the desk-buddy state payloads."""

    def __init__(self, activity: Optional[ActivityService] = None):
        self.activity = activity or activity_service
        self.device = DeviceTelemetry()
        self._lyrics_window: Dict[str, Any] = self._empty_lyrics_window()
        self._lyrics_track: Any = None
        self._lyrics_track_key: Optional[str] = None
        self._lyrics_lock: Optional[asyncio.Lock] = None
        self._cover_art_key: Optional[str] = None

    @staticmethod
    def _empty_lyrics_window() -> Dict[str, Any]:
        return {
            "available": False,
            "synced": False,
            "instrumental": False,
            "source": None,
            "index": -1,
            "total": 0,
            "prev": "",
            "current": "",
            "next": "",
        }

    async def refresh_lyrics(self) -> Dict[str, Any]:
        """Refresh the lyrics window for the current track.

        Runs once per state tick, but only performs a network lookup when the
        track (title/artist/duration) actually changes.
        """

        from app.services.lyrics import lyrics_service, lyrics_window

        if self._lyrics_lock is None:
            self._lyrics_lock = asyncio.Lock()

        async with self._lyrics_lock:
            music = self._music_dict()
            title = str(music.get("title") or "").strip()
            artist = str(music.get("artist") or "").strip()
            duration_ms = int(music.get("duration_ms") or 0)
            progress_ms = int(music.get("progress_ms") or 0)

            if not title:
                self._lyrics_window = self._empty_lyrics_window()
                self._lyrics_track = None
                self._lyrics_track_key = None
                self._cover_art_key = None
                return self._lyrics_window

            # Sync cover art independently of lyrics whenever the track changes.
            from app.services.cover_art import cover_art_service as _cas

            cover_key = _cas.cache_key(title, artist)
            if cover_key != self._cover_art_key:
                # _sync_cover_art sets self._cover_art_key itself before
                # dispatching, so don't set it here (the task would see a
                # matching key and return early without sending anything).
                asyncio.create_task(
                    self._sync_cover_art(title, artist, music.get("album_art_url"))
                )

            key = lyrics_service.cache_key(title, artist, duration_ms)
            if key != self._lyrics_track_key:
                self._lyrics_track_key = key
                # Fetch in the background so the state push is never blocked by
                # a slow LRCLIB request. The window updates on the next tick.
                async def _fetch() -> None:
                    try:
                        track = await lyrics_service.load(title, artist, duration_ms)
                        if self._lyrics_track_key == key:
                            self._lyrics_track = track
                            self._lyrics_window = lyrics_window(track, progress_ms)
                    except Exception:
                        pass

                asyncio.create_task(_fetch())
                # Keep showing the previous window until the fetch completes.
                self._lyrics_window = lyrics_window(self._lyrics_track, progress_ms)
                return self._lyrics_window

            self._lyrics_window = lyrics_window(self._lyrics_track, progress_ms)
            return self._lyrics_window

    async def _sync_cover_art(
        self, title: str, artist: str, album_art_url: Optional[str] = None
    ) -> None:
        """Fetch and send 40x40 thumbnail and 32x40 blurred background to the device."""
        if not title:
            return

        key = f"{title.strip().lower()}|{artist.strip().lower()}"
        if key == self._cover_art_key:
            return
        self._cover_art_key = key

        try:
            from app.services.cover_art import cover_art_service

            assets = await cover_art_service.get_cover_assets(
                title, artist, album_art_url
            )
            if not assets:
                return

            from app.services.hardware_bridge import hardware_bridge

            if hardware_bridge.is_connected:
                # 1. Send 40x40 thumbnail for PAGE_MUSIC
                await hardware_bridge.send_command(
                    "cover_thumb",
                    {"track": title[:32], "data": assets["thumb_b64"],
                     "dominant_color": assets.get("dominant_color")},
                )
                # 2. Send 32x40 blurred background for PAGE_LYRICS
                await hardware_bridge.send_command(
                    "cover_bg",
                    {"track": title[:32], "w": 32, "h": 40, "data": assets["bg_b64"]},
                )
                logger.info("Dispatched cover art to device for track: %s", title)
        except Exception as exc:
            logger.debug("Failed to dispatch cover art: %s", exc)

    def clear_cover_art_cache(self) -> None:
        """Clear the cover art cache to force re-sync on next track change or state push."""
        self._cover_art_key = None

    async def force_cover_art_sync(self) -> None:
        """Force immediate cover art re-sync for the currently playing track."""
        self._cover_art_key = None
        summary = self.get_summary()
        music = summary.get("music", {})
        title = music.get("title")
        artist = music.get("artist")
        album_art_url = music.get("album_art_url")
        # Sync if we have a title (artist may be empty but album_art_url might exist)
        if title:
            await self._sync_cover_art(title, artist or "", album_art_url)

    def _resolve_cover_cached(self, title: str, artist: str) -> str:
        try:
            from app.services.cover_art import _URL_CACHE, CoverArtService

            key = CoverArtService.cache_key(title, artist)
            return _URL_CACHE.get(key, "")
        except Exception:
            return ""

    def get_lyrics_window(self) -> Dict[str, Any]:
        return dict(self._lyrics_window)

    def get_full_lyrics(self) -> Dict[str, Any]:
        """Full lyrics sheet for the web dashboard (device only gets 3 lines)."""

        track = self._lyrics_track
        if track is None or not track.available:
            return {"available": False, "synced": False, "lines": []}
        return {
            "available": True,
            "synced": track.synced,
            "instrumental": track.instrumental,
            "source": track.source,
            "title": track.title,
            "artist": track.artist,
            "album": track.album,
            "duration_ms": track.duration_ms,
            "lines": [
                {"time_ms": line.time_ms, "text": line.text} for line in track.lines
            ],
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.activity.running

    async def start(self) -> None:
        await self.activity.start()

    async def stop(self) -> None:
        await self.activity.stop()

    # ------------------------------------------------------------------
    # Device telemetry
    # ------------------------------------------------------------------
    def touch_device(self) -> None:
        now = time.monotonic()
        self.device.last_seen = now
        self.device.last_heartbeat = now

    @property
    def device_online(self) -> bool:
        if self.device.last_seen is None:
            return False
        timeout = float(getattr(settings, "companion_device_timeout", 15.0))
        return (time.monotonic() - self.device.last_seen) <= timeout

    def device_heartbeat_age_ms(self) -> Optional[int]:
        if self.device.last_seen is None:
            return None
        return int((time.monotonic() - self.device.last_seen) * 1000)

    async def handle_device_message(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Update telemetry and turn device actions into broadcast events."""

        if not isinstance(message, dict):
            return []

        msg_type = message.get("type") or message.get("cmd") or ""
        events: List[Dict[str, Any]] = []

        if msg_type == "sensor_data":
            data = message.get("data") if isinstance(message.get("data"), dict) else message
            self.touch_device()

            for key in ("temperature", "temp"):
                if key in data:
                    self.device.sensors["temperature"] = float(data[key])
            for key in ("humidity", "pressure"):
                if key in data:
                    self.device.sensors[key] = float(data[key])
            if "battery" in data:
                self.device.battery = float(data["battery"])
            if "battery_voltage" in data:
                self.device.battery = float(data["battery_voltage"])
            if "battery_pct" in data:
                self.device.battery_pct = float(data["battery_pct"])
            if "battery_charging" in data:
                self.device.battery_charging = int(data["battery_charging"])
            if "mic_level" in data:
                self.device.mic_level = int(data["mic_level"])

            accel = data.get("accel")
            if isinstance(accel, dict):
                self.device.accel = {
                    axis: float(accel.get(axis, 0.0)) for axis in ("x", "y", "z")
                }

            events.append({"channel": "sensor_data", "data": message})

        elif msg_type == "inspection_data":
            self.touch_device()
            data = message.get("data") if isinstance(message.get("data"), dict) else message
            x = data.get("x", [])
            y = data.get("y", [])
            z = data.get("z", [])
            sample_rate = int(data.get("sample_rate_hz", 1000))
            method = data.get("method", "auto")

            if len(x) >= 3 and len(x) == len(y) == len(z):
                try:
                    from app.services.vibration import analyze
                    result = await analyze(x, y, z, sample_rate_hz=sample_rate, method=method)
                    events.append({"channel": "inspection_result", "data": result})
                    # Also send result back to device
                    from app.services.hardware_bridge import hardware_bridge
                    if hardware_bridge.is_connected:
                        await hardware_bridge.send_command("inspection_result", result)
                except Exception as exc:
                    logger.exception("Inspection analysis failed: %s", exc)
            else:
                logger.warning("Invalid inspection data: x=%d y=%d z=%d", len(x), len(y), len(z))

        elif msg_type in ("heartbeat", "pong"):
            self.touch_device()
            if message.get("page"):
                self.device.page = _clean(message["page"], 24)
            if message.get("mode"):
                self.device.mode = _clean(message["mode"], 24)
            if message.get("expression"):
                self.device.expression = _clean(message["expression"], 24)
            if message.get("firmware"):
                self.device.firmware = _clean(message["firmware"], 24)

        elif msg_type in ("button", "device_event"):
            self.touch_device()
            if message.get("page"):
                self.device.page = _clean(message["page"], 24)
            if message.get("mode"):
                self.device.mode = _clean(message["mode"], 24)

            button = _clean(message.get("button") or message.get("action"), 24)
            events.extend(await self._handle_button(button))
            events.append({"channel": "device_event", "data": message})

        elif msg_type == "music":
            events.extend(await self._handle_music(message))

        elif msg_type == "pomodoro":
            events.extend(await self._handle_pomodoro(message))

        elif msg_type == "mode_switched":
            self.touch_device()
            self.device.mode = _clean(message.get("mode") or message.get("payload"), 24)
            events.append({"channel": "device_event", "data": message})

        elif msg_type == "gesture":
            self.touch_device()
            gesture = _clean(message.get("gesture"), 24) or "unknown"
            self.device.last_gesture = gesture
            self.device.last_gesture_at = datetime.utcnow()
            if message.get("page"):
                self.device.page = _clean(message["page"], 24)
            if message.get("mode"):
                self.device.mode = _clean(message["mode"], 24)
            events.append(
                {
                    "channel": "gesture",
                    "data": {"gesture": gesture, "timestamp": datetime.utcnow().isoformat()},
                }
            )
            events.append({"channel": "device_event", "data": message})

        elif msg_type == "notification_ack":
            self.touch_device()
            notification_id = _clean(message.get("id"), 48)
            if notification_id:
                from app.services.deskmate import deskmate_service

                deskmate_service.mark_read(notification_id)
            events.append({"channel": "device_event", "data": message})

        elif msg_type == "status":
            self.touch_device()
            firmware = message.get("firmware") or message.get("version")
            if firmware:
                self.device.firmware = _clean(firmware, 24)
            events.append({"channel": "device_event", "data": message})

        else:
            logger.debug("Unhandled device message: %s", msg_type)

        return events

    async def _handle_button(self, button: str) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        if button == "voice":
            events.append(
                {
                    "channel": "voice_requested",
                    "data": {"source": "device", "timestamp": datetime.utcnow().isoformat()},
                }
            )
            return events

        if button != "select":
            return events

        page = self.device.page
        try:
            if page == "music":
                from app.services.music import music_controller

                status = music_controller.get_status()
                if getattr(status, "playing", False):
                    await music_controller.pause()
                else:
                    await music_controller.play()
                events.append(
                    {"channel": "music", "data": _dataclass_dict(music_controller.get_status())}
                )

            elif page == "pomodoro":
                from app.services.deskmate import deskmate_service

                status = deskmate_service.get_pomodoro_status()
                if status.get("running"):
                    result = deskmate_service.pause_pomodoro()
                else:
                    result = deskmate_service.start_pomodoro()
                events.append({"channel": "pomodoro", "data": result})

            elif page == "notifications":
                from app.services.deskmate import deskmate_service

                unread = deskmate_service.get_notifications(unread_only=True, limit=1)
                if unread:
                    deskmate_service.mark_read(unread[0].id)
                    events.append(
                        {
                            "channel": "notifications",
                            "data": {"id": unread[0].id, "read": True},
                        }
                    )
        except Exception:
            logger.exception("Device select action failed on page %s", page)

        return events

    async def _handle_music(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        action = _clean(message.get("action"), 24).lower()
        level = message.get("level")

        try:
            from app.services.music import music_controller

            if action == "play":
                await music_controller.play()
            elif action == "pause":
                await music_controller.pause()
            elif action in ("next", "next_track"):
                await music_controller.next_track()
            elif action in ("prev", "previous", "previous_track"):
                await music_controller.previous_track()
            elif action == "volume" and level is not None:
                await music_controller.set_volume(int(level))
            elif action in ("volume_up", "vol_up", "volume_down", "vol_down"):
                status = music_controller.get_status()
                current = getattr(status, "volume", None)
                if current is None and isinstance(status, dict):
                    current = status.get("volume")
                current = int(current if current is not None else 50)
                step = 5 if action in ("volume_up", "vol_up") else -5
                await music_controller.set_volume(max(0, min(100, current + step)))
            else:
                logger.debug("Unknown music action: %s", action)
                return []

            return [
                {
                    "channel": "music",
                    "data": _dataclass_dict(music_controller.get_status()),
                }
            ]
        except Exception:
            logger.exception("Music action failed: %s", action)
            return []

    async def _handle_pomodoro(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        action = _clean(message.get("action"), 24).lower()
        minutes = int(message.get("minutes", 25) or 25)

        try:
            from app.services.deskmate import deskmate_service

            if action == "start":
                result = deskmate_service.start_pomodoro(minutes)
            elif action == "pause":
                result = deskmate_service.pause_pomodoro()
            elif action == "reset":
                result = deskmate_service.reset_pomodoro(minutes)
            else:
                logger.debug("Unknown pomodoro action: %s", action)
                return []

            return [{"channel": "pomodoro", "data": result}]
        except Exception:
            logger.exception("Pomodoro action failed: %s", action)
            return []

    # ------------------------------------------------------------------
    # State payloads
    # ------------------------------------------------------------------
    def _music_dict(self) -> Dict[str, Any]:
        try:
            from app.services.remote_pc import remote_pc

            remote_music = remote_pc.get("music") if remote_pc.fresh() else None
            if isinstance(remote_music, dict) and remote_music:
                base = {
                    "playing": False,
                    "title": "",
                    "artist": "",
                    "album": "",
                    "progress_ms": 0,
                    "duration_ms": 0,
                    "volume": 50,
                    "provider": "remote",
                }
                base.update(remote_music)
                return base
        except Exception:
            pass

        try:
            from app.services.music import music_controller

            return _dataclass_dict(music_controller.get_status())
        except Exception:
            return {
                "playing": False,
                "title": "",
                "artist": "",
                "album": "",
                "progress_ms": 0,
                "duration_ms": 0,
                "volume": 50,
                "provider": "unknown",
            }

    def _metrics_dict(self) -> Dict[str, Any]:
        metrics: Dict[str, Any] = {}
        try:
            from app.services.remote_pc import remote_pc

            remote_metrics = remote_pc.get("metrics") if remote_pc.fresh() else None
            if isinstance(remote_metrics, dict) and remote_metrics:
                metrics = remote_metrics
        except Exception:
            metrics = {}

        if not metrics:
            try:
                from app.services.system_monitor import system_monitor

                metrics = system_monitor.get_metrics() or {}
            except Exception:
                metrics = {}

        return {
            "cpu_percent": metrics.get("cpu_percent"),
            "memory_percent": metrics.get("memory_percent"),
            "gpu_percent": metrics.get("gpu_percent"),
            "cpu_temp_c": metrics.get("cpu_temp_c"),
            "cpu_temp_source": metrics.get("cpu_temp_source"),
            "thermal_zone_c": metrics.get("thermal_zone_c"),
            "gpu_temp_c": metrics.get("gpu_temp_c"),
            "gpu_memory_percent": metrics.get("gpu_memory_percent"),
            "gpu_memory_used_mb": metrics.get("gpu_memory_used_mb"),
            "gpu_memory_total_mb": metrics.get("gpu_memory_total_mb"),
            "gpu_fan_percent": metrics.get("gpu_fan_percent"),
            "gpu_name": metrics.get("gpu_name"),
            "gpu_source": metrics.get("gpu_source"),
            "disk_percent": metrics.get("disk_percent"),
        }

    def _pomodoro_dict(self) -> Dict[str, Any]:
        try:
            from app.services.deskmate import deskmate_service

            return deskmate_service.get_pomodoro_status()
        except Exception:
            return {
                "running": False,
                "is_break": False,
                "remaining_seconds": 25 * 60,
                "duration_seconds": 25 * 60,
            }

    def _unread_count(self) -> int:
        try:
            from app.services.deskmate import deskmate_service

            return deskmate_service.get_unread_count()
        except Exception:
            return 0

    def get_context(self, force: bool = False) -> Dict[str, Any]:
        """Full context, used by the REST API and WebSocket clients."""

        context = self.activity.get_context(force=force)
        context["device"] = {
            "online": self.device_online,
            "heartbeat_age_ms": self.device_heartbeat_age_ms(),
            "page": self.device.page,
            "mode": self.device.mode,
            "battery": self.device.battery,
            "battery_voltage": self.device.battery,
            "battery_percent": self.device.battery_pct,
            "battery_charging": self.device.battery_charging,
            "mic_level": self.device.mic_level,
            "firmware": self.device.firmware,
            "last_gesture": self.device.last_gesture,
            "last_gesture_at": (
                self.device.last_gesture_at.isoformat()
                if self.device.last_gesture_at
                else None
            ),
            "sensors": dict(self.device.sensors),
        }
        return context

    def get_summary(self) -> Dict[str, Any]:
        """Readable summary for the web dashboard."""

        context = self.get_context()
        music = self._music_dict()
        metrics = self._metrics_dict()
        pomodoro = self._pomodoro_dict()
        now = datetime.now()

        # The web panel can remap activity -> OLED face expression.
        expression = context.get("expression")
        try:
            from app.services.device_settings import store as device_store
            mapped = device_store.expressions().get(str(context.get("activity")))
            if mapped:
                expression = mapped
        except Exception:  # pragma: no cover - settings are optional
            pass

        return {
            "activity": context.get("activity"),
            "expression": expression,
            "sleep_stage": context.get("sleep_stage"),
            "app": context.get("app"),
            "window": context.get("window"),
            "idle_seconds": context.get("idle_seconds"),
            "audio_active": context.get("audio_active"),
            "description": context.get("description"),
            "clock": now.strftime("%H:%M"),
            "date": now.strftime("%d %b"),
            "dow": now.strftime("%a"),
            "epoch": int(now.timestamp()),
            "music": {
                "playing": bool(music.get("playing", False)),
                "title": music.get("title", ""),
                "artist": music.get("artist", ""),
                "album": music.get("album", ""),
                "album_art_url": music.get("album_art_url") or self._resolve_cover_cached(music.get("title", ""), music.get("artist", "")),
                "progress_ms": music.get("progress_ms", 0),
                "duration_ms": music.get("duration_ms", 0),
                "volume": music.get("volume", 50),
                "provider": music.get("provider", "unknown"),
            },
            "metrics": metrics,
            "pomodoro": pomodoro,
            "lyrics": dict(self._lyrics_window),
            "environment": {
                "temperature": self.device.sensors.get("temperature"),
                "humidity": self.device.sensors.get("humidity"),
                "pressure": self.device.sensors.get("pressure"),
            },
            "microphone": {
                "available": self.device.mic_level >= 0,
                "level": self.device.mic_level,
            },
            "device": context.get("device"),
            "unread": self._unread_count(),
            "thresholds": context.get("thresholds"),
            "timestamp": now.isoformat(),
        }

    def get_device_state(self, summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Flat, compact payload optimised for the Arduino JSON parser."""

        summary = summary or self.get_summary()
        music = summary["music"]
        metrics = summary["metrics"]
        pomodoro = summary["pomodoro"]
        environment = summary["environment"]
        device = summary["device"]
        lyrics = summary.get("lyrics") or {}

        progress = int(music.get("progress_ms") or 0) // 1000
        duration = int(music.get("duration_ms") or 0) // 1000
        battery_pct = device.get("battery_percent")
        try:
            battery_pct = int(round(float(battery_pct)))
        except (TypeError, ValueError):
            battery_pct = -1
        battery_charging = device.get("battery_charging")
        try:
            battery_charging = int(battery_charging)
        except (TypeError, ValueError):
            battery_charging = -1
        mic_level = device.get("mic_level")
        try:
            mic_level = int(mic_level)
        except (TypeError, ValueError):
            mic_level = -1

        return {
            "act": summary["activity"],
            "expr": summary["expression"],
            "sleep": summary["sleep_stage"],
            "app": _clean(summary["app"], 32),
            "win": _clean(summary["window"], 72),
            "idle": int(summary["idle_seconds"] or 0),
            "audio": 1 if summary["audio_active"] else 0,
            "cpu": _round_or(metrics.get("cpu_percent"), -1),
            "mem": _round_or(metrics.get("memory_percent"), -1),
            "gpu": _round_or(metrics.get("gpu_percent"), -1),
            "ctemp": _round_or(metrics.get("cpu_temp_c"), -1),
            "tz": _round_or(metrics.get("thermal_zone_c"), -1),
            "gtemp": _round_or(metrics.get("gpu_temp_c"), -1),
            "gmem": _round_or(metrics.get("gpu_memory_percent"), -1),
            "gvram": int(metrics.get("gpu_memory_total_mb") or 0),
            "gfan": _round_or(metrics.get("gpu_fan_percent"), -1),
            "m_title": _clean(music.get("title"), 64),
            "m_artist": _clean(music.get("artist"), 48),
            "m_play": 1 if music.get("playing") else 0,
            "m_prog": progress,
            "m_dur": duration,
            "lyr_ok": 1 if lyrics.get("available") else 0,
            "lyr_sync": 1 if lyrics.get("synced") else 0,
            "lyr_idx": int(lyrics.get("index") or -1),
            "lyr_tot": int(lyrics.get("total") or 0),
            "lyr_prev": _clean(lyrics.get("prev"), 64),
            "lyr_cur": _clean(lyrics.get("current"), 64),
            "lyr_next": _clean(lyrics.get("next"), 64),
            "pomo_run": 1 if pomodoro.get("running") else 0,
            "pomo_rem": int(pomodoro.get("remaining_seconds") or 0),
            "pomo_break": 1 if pomodoro.get("is_break") else 0,
            "env_t": _round_or(environment.get("temperature"), -999),
            "env_h": _round_or(environment.get("humidity"), -999),
            "env_p": _round_or(environment.get("pressure"), -999),
            "batt": battery_pct,
            "batt_v": round(float(device.get("battery_voltage") or 0.0), 1),
            "batt_chg": battery_charging,
            "mic": mic_level,
            "unread": int(summary["unread"]),
            "clock": summary["clock"],
            "date": summary["date"],
            "dow": summary["dow"],
            "epoch": summary["epoch"],
            "dev_online": 1 if device.get("online") else 0,
            "mode": _clean(device.get("mode"), 16),
            "page": _clean(device.get("page"), 16),
        }

    # ------------------------------------------------------------------
    # Outbound device messages
    # ------------------------------------------------------------------
    async def push_notification(
        self,
        title: str,
        message: str,
        priority: int = 1,
        notification_id: Optional[str] = None,
    ) -> bool:
        from app.services.hardware_bridge import hardware_bridge

        if not hardware_bridge.is_connected:
            return False

        return await hardware_bridge.send_command(
            "notification",
            {
                "id": _clean(notification_id, 48),
                "title": _clean(title, 48),
                "message": _clean(message, 96),
                "priority": int(priority),
            },
        )

    async def push_pomodoro(self, action: str, minutes: int = 25) -> bool:
        from app.services.hardware_bridge import hardware_bridge

        if not hardware_bridge.is_connected:
            return False

        return await hardware_bridge.send_command(
            "pomodoro",
            {"action": action, "minutes": minutes},
        )

    async def push_music(self, action: str, level: Optional[int] = None) -> bool:
        from app.services import serial_manager as serial_state

        manager = serial_state.get_serial_manager()
        if not manager or not manager.is_connected:
            return False

        payload: Dict[str, Any] = {"action": action}
        if level is not None:
            payload["level"] = int(level)
        return await manager.send_command("music", payload)


def _dataclass_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {}


def _round_or(value: Any, fallback: float) -> float:
    try:
        if value is None:
            return fallback
        return round(float(value), 1)
    except (TypeError, ValueError):
        return fallback


# Shared instance used by the API, WebSocket layer and serial reader.
companion_service = CompanionService()
