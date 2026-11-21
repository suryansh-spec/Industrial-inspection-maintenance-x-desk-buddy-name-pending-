"""
DeskBuddy companion API.

Exposes the PC-context/expression state used by the OLED face and the TFT
dashboard. The same state is broadcast over ``/ws`` on the
``deskbuddy_state`` channel and pushed over serial to the ESP32.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.activity import Expression
from app.services.companion import companion_service

router = APIRouter(prefix="/companion", tags=["companion"])


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
