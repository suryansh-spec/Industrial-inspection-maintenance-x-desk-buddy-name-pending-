"""
Desktop Tools API - PC monitoring, music, calendar, notifications.
"""
import asyncio
import platform
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from desktop_bridge.main import pc_monitor, music_controller, calendar_service

router = APIRouter(prefix="/desktop", tags=["desktop"])


# ========================================================================
# PC Monitoring
# ========================================================================

class PCMetrics(BaseModel):
    timestamp: str
    cpu_percent: float
    cpu_per_core: List[float]
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    network_sent_mb: float
    network_recv_mb: float
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    cpu_temp_c: Optional[float] = None


@router.get("/pc/metrics", response_model=PCMetrics)
async def get_pc_metrics():
    """Get current PC hardware metrics."""
    from desktop_bridge.main import pc_monitor
    
    if not pc_monitor:
        raise HTTPException(status_code=503, detail="PC monitoring not enabled")
    
    return pc_monitor.get_metrics()


@router.get("/pc/metrics/history")
async def get_metrics_history(
    duration_minutes: int = Query(default=60, ge=1, le=1440)
):
    """Get historical metrics for charting."""
    from desktop_bridge.main import pc_monitor
    
    if not pc_monitor:
        raise HTTPException(status_code=503, detail="PC monitoring not enabled")
    
    return pc_monitor.get_history(duration_minutes)


@router.get("/pc/processes")
async def get_top_processes(limit: int = Query(default=10, ge=1, le=50)):
    """Get top processes by CPU/memory usage."""
    from desktop_bridge.main import pc_monitor
    
    if not pc_monitor:
        raise HTTPException(status_code=503, detail="PC monitoring not enabled")
    
    return pc_monitor.get_top_processes(limit)


# ========================================================================
# Music Control
# ========================================================================

class MusicStatus(BaseModel):
    playing: bool
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    progress_ms: int = 0
    duration_ms: int = 0
    volume: int = 50
    shuffle: bool = False
    repeat: str = "off"


class VolumeRequest(BaseModel):
    level: int = Field(..., ge=0, le=100)


@router.get("/music/status", response_model=MusicStatus)
async def get_music_status():
    """Get current music playback status."""
    from desktop_bridge.main import music_controller
    
    if not music_controller:
        raise HTTPException(status_code=503, detail="Music control not enabled")
    
    return music_controller.get_status()


@router.post("/music/play")
async def play_music():
    """Play/resume music."""
    from desktop_bridge.main import music_controller
    
    if not music_controller:
        raise HTTPException(status_code=503, detail="Music control not enabled")
    
    await music_controller.play()
    return {"status": "playing"}


@router.post("/music/pause")
async def pause_music():
    """Pause music."""
    from desktop_bridge.main import music_controller
    
    if not music_controller:
        raise HTTPException(status_code=503, detail="Music control not enabled")
    
    await music_controller.pause()
    return {"status": "paused"}


@router.post("/music/next")
async def next_track():
    """Skip to next track."""
    from desktop_bridge.main import music_controller
    
    if not music_controller:
        raise HTTPException(status_code=503, detail="Music control not enabled")
    
    await music_controller.next_track()
    return {"status": "next"}


@router.post("/music/previous")
async def previous_track():
    """Go to previous track."""
    from desktop_bridge.main import music_controller
    
    if not music_controller:
        raise HTTPException(status_code=503, detail="Music control not enabled")
    
    await music_controller.previous_track()
    return {"status": "previous"}


@router.post("/music/volume")
async def set_volume(request: VolumeRequest):
    """Set volume level (0-100)."""
    from desktop_bridge.main import music_controller
    
    if not music_controller:
        raise HTTPException(status_code=503, detail="Music control not enabled")
    
    await music_controller.set_volume(request.level)
    return {"status": "volume_set", "level": request.level}


# ========================================================================
# Calendar
# ========================================================================

class CalendarEvent(BaseModel):
    id: str
    title: str
    start: str
    end: str
    location: Optional[str] = None
    description: Optional[str] = None
    all_day: bool = False


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start: str = Field(..., description="ISO format datetime")
    end: str = Field(..., description="ISO format datetime")
    location: Optional[str] = None
    description: Optional[str] = None
    all_day: bool = False


@router.get("/calendar/events", response_model=List[CalendarEvent])
async def get_calendar_events(
    days: int = Query(default=7, ge=1, le=90),
    start_date: Optional[str] = None
):
    """Get upcoming calendar events."""
    from desktop_bridge.main import calendar_service
    
    if not calendar_service:
        raise HTTPException(status_code=503, detail="Calendar not enabled")
    
    start = datetime.fromisoformat(start_date) if start_date else datetime.now()
    end = start + timedelta(days=days)
    
    return await calendar_service.get_events(start, end)


@router.post("/calendar/events", response_model=CalendarEvent)
async def create_calendar_event(event: EventCreate):
    """Create new calendar event."""
    from desktop_bridge.main import calendar_service
    
    if not calendar_service:
        raise HTTPException(status_code=503, detail="Calendar not enabled")
    
    return await calendar_service.create_event(event)


@router.get("/calendar/next")
async def get_next_event():
    """Get next upcoming event."""
    from desktop_bridge.main import calendar_service
    
    if not calendar_service:
        raise HTTPException(status_code=503, detail="Calendar not enabled")
    
    event = await calendar_service.get_next_event()
    if not event:
        return {"event": None}
    return {"event": event}


# ========================================================================
# Notifications
# ========================================================================

class Notification(BaseModel):
    id: str
    title: str
    message: str
    type: str = "info"  # info, warning, error, success
    timestamp: str
    read: bool = False
    actions: List[dict] = []


@router.get("/notifications")
async def get_notifications(unread_only: bool = False, limit: int = 50):
    """Get notifications."""
    # In a real implementation, this would come from a notification store
    return {
        "notifications": [
            {
                "id": "notif_1",
                "title": "Inspection Complete",
                "message": "Vibration analysis completed: Normal",
                "type": "success",
                "timestamp": datetime.now().isoformat(),
                "read": False,
                "actions": [{"label": "View", "action": "view_inspection"}]
            }
        ],
        "unread_count": 1
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """Mark notification as read."""
    return {"status": "marked_read", "id": notification_id}


# ========================================================================
# System
# ========================================================================

class SystemInfo(BaseModel):
    platform: str
    platform_version: str
    architecture: str
    processor: str
    python_version: str
    hostname: str
    uptime_seconds: float


@router.get("/system/info", response_model=SystemInfo)
async def get_system_info():
    """Get system information."""
    import psutil
    import socket
    
    return SystemInfo(
        platform=platform.system(),
        platform_version=platform.version(),
        architecture=platform.machine(),
        processor=platform.processor(),
        python_version=platform.python_version(),
        hostname=socket.gethostname(),
        uptime_seconds=psutil.boot_time()
    )


@router.get("/system/env")
async def get_environment():
    """Get environment info (sanitized)."""
    import os
    
    # Only return safe environment variables
    safe_keys = ["PATH", "HOME", "USER", "SHELL", "LANG", "PYTHONPATH"]
    env = {k: os.environ.get(k, "") for k in safe_keys if k in os.environ}
    return {"environment": env}