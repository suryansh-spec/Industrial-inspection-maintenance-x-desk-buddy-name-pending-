"""
Omnipect companion API.

Exposes the PC-context/expression state used by the OLED face and the TFT
dashboard. The same state is broadcast over ``/ws`` on the
``deskbuddy_state`` channel and pushed over serial to the ESP32.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.activity import Expression
from app.services.companion import companion_service
from app.services.remote_pc import remote_pc

router = APIRouter(prefix="/companion", tags=["companion"])


class PCStateRequest(BaseModel):
    """PC state pushed by ``pc_agent/pc_agent.py`` when the backend runs in the cloud."""

    app: str = ""
    window: str = ""
    pid: int = 0
    idle_seconds: float = 0.0
    audio_active: bool = False
    metrics: Optional[Dict[str, Any]] = None
    music: Optional[Dict[str, Any]] = None


@router.post("/pc-state")
async def push_pc_state(
    request: PCStateRequest,
    x_agent_token: Optional[str] = Header(default=None),
):
    """Receive the PC's foreground app, idle time, metrics and music from the PC agent."""

    if settings.agent_token and x_agent_token != settings.agent_token:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    remote_pc.update(request.model_dump())
    companion_service.activity.touch_heartbeat()
    return {"status": "ok"}


@router.get("/pc-state")
async def get_pc_state():
    """Debug view of the last state pushed by the PC agent."""

    return remote_pc.snapshot()


class EmotionRequest(BaseModel):
    expression: str = Field(..., description="One of the values from GET /companion/expressions")
    duration_seconds: float = Field(
        default=30.0,
        ge=0,
        le=3600,
        description="How long to hold the manual expression; 0 means indefinitely",
    )


class HeartbeatResponse(BaseModel):
    status: str
    heartbeat_age_ms: int


@router.get("/context")
async def get_context(force: bool = Query(default=False)):
    """Return the current PC activity, sleep stage and device context."""

    return companion_service.get_context()


@router.get("/summary")
async def get_summary():
    """Readable combined state for dashboards and debugging."""

    return companion_service.get_summary()


@router.get("/device-state")
async def get_device_state():
    """Flat state payload exactly as sent to the Arduino firmware."""

    return companion_service.get_device_state()


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat():
    """Register a heartbeat from the PC bridge or an external agent."""

    companion_service.activity.touch_heartbeat()
    return HeartbeatResponse(
        status="ok",
        heartbeat_age_ms=companion_service.activity.heartbeat_age_ms(),
    )


@router.post("/emotion")
async def set_emotion(request: EmotionRequest):
    """Temporarily override the face expression."""

    try:
        expression = companion_service.activity.set_manual_expression(
            request.expression,
            request.duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "ok",
        "expression": expression.value,
        "duration_seconds": request.duration_seconds,
        "context": companion_service.get_context(force=True),
    }


@router.delete("/emotion")
async def clear_emotion():
    """Clear a manual expression override."""

    companion_service.activity.clear_manual_expression()
    return {"status": "cleared", "context": companion_service.get_context(force=True)}


@router.get("/expressions")
async def list_expressions() -> Dict[str, List[str]]:
    """List every expression the firmware understands."""

    return {"expressions": [expression.value for expression in Expression]}


@router.get("/thresholds")
async def get_thresholds():
    """Return the inactivity thresholds used by the sleep engine."""

    return companion_service.activity.thresholds


@router.put("/thresholds")
async def update_thresholds(values: Dict[str, Any]):
    """Persist and apply the inactivity thresholds edited in the web panel."""

    from app.services.device_settings import store

    current = store.get("sleep_thresholds") or {}
    for key in ("sleepy_seconds", "sleep_seconds", "deep_sleep_seconds"):
        if key in (values or {}):
            current[key] = values[key]
    store.replace("sleep_thresholds", current)
    return companion_service.activity.set_thresholds(current)
