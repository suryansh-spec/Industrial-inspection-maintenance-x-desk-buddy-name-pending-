"""
Desktop Tools API endpoints (PC monitoring, music, calendar, notifications).
"""
import platform
import socket
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.calendar import calendar_service
from app.services.companion import companion_service
from app.services.deskmate import deskmate_service
from app.services.music import music_controller
from app.services.system_monitor import system_monitor
from app.ws.manager import ws_manager

router = APIRouter(prefix="/desktop", tags=["desktop"])


# ========================================================================
# PC Monitoring
# ========================================================================

class PCMetricsResponse(BaseModel):
    timestamp: str
    cpu_percent: float
    cpu_per_core: List[float]
    cpu_freq_current: Optional[float] = None
    cpu_freq_min: Optional[float] = None
    cpu_freq_max: Optional[float] = None
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    memory_available_gb: float = 0.0
    swap_percent: float = 0.0
    swap_used_gb: float = 0.0
    swap_total_gb: float = 0.0
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    disk_free_gb: float = 0.0
    disk_read_mb_s: float = 0.0
    disk_write_mb_s: float = 0.0
    network_sent_mb_s: float = 0.0
    network_recv_mb_s: float = 0.0
    network_sent_total_mb: float = 0.0
    network_recv_total_mb: float = 0.0
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None
    gpu_memory_used_mb: Optional[int] = None
    gpu_memory_total_mb: Optional[int] = None
    gpu_temp_c: Optional[float] = None
    gpu_fan_percent: Optional[float] = None
    gpu_name: Optional[str] = None
    gpu_source: Optional[str] = None
    cpu_temp_c: Optional[float] = None
    cpu_temp_source: Optional[str] = None
    thermal_zone_c: Optional[float] = None
    process_count: int
    thread_count: int
    boot_time: Optional[str] = None
    top_processes: List[Dict[str, Any]] = []


@router.get("/pc/metrics", response_model=PCMetricsResponse)
async def get_pc_metrics():
    """Get current PC hardware metrics."""
    metrics = system_monitor.get_metrics()
    if not metrics:
        raise HTTPException(status_code=503, detail="Metrics not available")

    payload = dict(metrics)
    payload.setdefault("timestamp", datetime.utcnow().isoformat())
    return PCMetricsResponse(**payload)


@router.get("/pc/metrics/history")
async def get_metrics_history(
    duration_minutes: int = Query(default=60, ge=1, le=1440)
):
    """Get historical metrics for charting."""
    return system_monitor.get_history(duration_minutes)


@router.get("/pc/processes")
async def get_top_processes(limit: int = Query(default=10, ge=1, le=50)):
    """Get top processes by CPU/memory usage."""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes.sort(key=lambda p: p.get("cpu_percent") or 0.0, reverse=True)
    return {"processes": processes[:limit]}


@router.get("/pc/alerts")
async def get_pc_alerts():
    """Get current PC alert status."""
    return system_monitor.get_alert_status()


# ========================================================================
# Music Control
# ========================================================================

class MusicStatusResponse(BaseModel):
    playing: bool
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    progress_ms: int = 0
    duration_ms: int = 0
    volume: int = 50
    shuffle: bool = False
    repeat: str = "off"
    provider: Optional[str] = None


class VolumeRequest(BaseModel):
    level: int = Field(..., ge=0, le=100)


def _music_status_dict() -> Dict[str, Any]:
    status = music_controller.get_status()
    if hasattr(status, "__dict__"):
        return {k: v for k, v in vars(status).items() if not k.startswith("_")}
    return dict(status)


@router.get("/music/status", response_model=MusicStatusResponse)
async def get_music_status():
    """Get current music playback status."""
    return MusicStatusResponse(**_music_status_dict())


@router.get("/music/lyrics")
async def get_music_lyrics():
    """Current previous/current/next lyric lines for the playing track.

    The lookup only hits LRCLIB when the track changed; repeated calls are
    served from the in-memory cache.
    """
    window = await companion_service.refresh_lyrics()
    status = _music_status_dict()
    return {
        "track": {
            "title": status.get("title", ""),
            "artist": status.get("artist", ""),
            "album": status.get("album", ""),
            "playing": bool(status.get("playing", False)),
            "progress_ms": int(status.get("progress_ms") or 0),
            "duration_ms": int(status.get("duration_ms") or 0),
        },
        "lyrics": window,
    }


@router.get("/music/lyrics/full")
async def get_music_lyrics_full():
    """Full cached lyric sheet for the current track (web dashboards)."""
    await companion_service.refresh_lyrics()
    return companion_service.get_full_lyrics()


@router.post("/music/play")
async def play_music():
    """Play/resume music."""
    await music_controller.play()
    return {"status": "playing"}


@router.post("/music/pause")
async def pause_music():
    """Pause music."""
    await music_controller.pause()
    return {"status": "paused"}


@router.post("/music/next")
async def next_track():
    """Skip to next track."""
    await music_controller.next_track()
    return {"status": "next"}


@router.post("/music/previous")
async def previous_track():
    """Go to previous track."""
    await music_controller.previous_track()
    return {"status": "previous"}


@router.post("/music/volume")
async def set_volume(request: VolumeRequest):
    """Set volume level (0-100)."""
    await music_controller.set_volume(request.level)
    return {"status": "volume_set", "level": request.level}


@router.get("/music/providers")
async def get_music_providers():
    """Get available music providers."""
    return music_controller.get_available_providers()


@router.post("/music/search")
async def search_youtube_music(q: str, limit: int = 10):
    """Search YouTube Music."""
    results = await music_controller.search_youtube_music(q, limit)
    return {"results": results}


# ========================================================================
# Calendar
# ========================================================================

class CalendarEventResponse(BaseModel):
    id: str
    title: str
    start: str
    end: str
    location: Optional[str] = None
    description: Optional[str] = None
    all_day: bool = False


class EventCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start: str = Field(..., description="ISO format datetime")
    end: str = Field(..., description="ISO format datetime")
    location: Optional[str] = None
    description: Optional[str] = None
    all_day: bool = False


@router.get("/calendar/events", response_model=List[CalendarEventResponse])
async def get_calendar_events(
    days: int = Query(default=7, ge=1, le=90),
    start_date: Optional[str] = None
):
    """Get upcoming calendar events."""
    start = datetime.fromisoformat(start_date) if start_date else datetime.now()
    end = start + timedelta(days=days)

    events = await calendar_service.get_events(start, end)
    return [e.to_dict() for e in events]


@router.get("/calendar/next", response_model=CalendarEventResponse)
async def get_next_calendar_event():
    """Get next upcoming event."""
    event = await calendar_service.get_next_event()
    if not event:
        raise HTTPException(status_code=404, detail="No upcoming events")

    return event.to_dict()


@router.post("/calendar/events", response_model=CalendarEventResponse)
async def create_calendar_event(event: EventCreateRequest):
    """Create new calendar event."""
    event_data = {
        "title": event.title,
        "start": event.start,
        "end": event.end,
        "location": event.location,
        "description": event.description,
        "all_day": event.all_day,
    }

    created = await calendar_service.create_event(event_data)
    return created.to_dict()


# ========================================================================
# Notifications
# ========================================================================

class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    timestamp: str
    read: bool = False
    actions: List[Dict[str, str]] = []


class NotificationCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(default="", max_length=500)
    type: str = Field(default="info", max_length=32)
    priority: int = Field(default=1, ge=0, le=3)


@router.post("/notifications", response_model=NotificationResponse)
async def create_notification(request: NotificationCreateRequest):
    """Create a notification and push it to the desk-buddy display."""

    notification = deskmate_service.add_notification(
        title=request.title,
        message=request.message,
        type=request.type,
        actions=[],
    )
    await ws_manager.broadcast("notifications", notification.to_dict())
    await companion_service.push_notification(
        notification.title,
        notification.message,
        priority=request.priority,
        notification_id=notification.id,
    )
    return notification.to_dict()


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50
):
    """Get notifications."""
    notifications = deskmate_service.get_notifications(
        unread_only=unread_only, limit=limit
    )
    return {
        "notifications": [n.to_dict() for n in notifications],
        "unread_count": deskmate_service.get_unread_count(),
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """Mark notification as read."""
    if not deskmate_service.mark_read(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "marked_read"}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str):
    """Dismiss notification."""
    if not deskmate_service.dismiss(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "dismissed"}


# ========================================================================
# Pomodoro
# ========================================================================

@router.get("/pomodoro/status")
async def get_pomodoro_status():
    """Get Pomodoro timer status."""
    return deskmate_service.get_pomodoro_status()


@router.post("/pomodoro/start")
async def start_pomodoro(minutes: int = Query(default=25, ge=1, le=180)):
    """Start a Pomodoro timer."""
    result = deskmate_service.start_pomodoro(minutes)
    await companion_service.push_pomodoro("start", minutes)
    return result


@router.post("/pomodoro/pause")
async def pause_pomodoro():
    """Pause the Pomodoro timer."""
    result = deskmate_service.pause_pomodoro()
    await companion_service.push_pomodoro("pause")
    return result


@router.post("/pomodoro/reset")
async def reset_pomodoro(minutes: int = Query(default=25, ge=1, le=180)):
    """Reset the Pomodoro timer."""
    result = deskmate_service.reset_pomodoro(minutes)
    await companion_service.push_pomodoro("reset", minutes)
    return result


# ========================================================================
# System Info
# ========================================================================

class SystemInfoResponse(BaseModel):
    platform: str
    platform_version: str
    architecture: str
    processor: str
    python_version: str
    hostname: str
    uptime_seconds: float


@router.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    """Get system information."""
    return SystemInfoResponse(
        platform=platform.system(),
        platform_version=platform.version(),
        architecture=platform.machine(),
        processor=platform.processor(),
        python_version=platform.python_version(),
        hostname=socket.gethostname(),
        uptime_seconds=time.time() - psutil.boot_time(),
    )


@router.get("/system/env")
async def get_environment():
    """Get environment info (sanitized)."""
    import os

    safe_keys = ["PATH", "HOME", "USER", "SHELL", "LANG", "PYTHONPATH"]
    env = {k: os.environ.get(k, "") for k in safe_keys if k in os.environ}
    return {"environment": env}
