"""
Vibration Analysis API - Proxies requests to backend API and handles local ML.
"""
import asyncio
import time
import uuid
from typing import Optional
import httpx
import numpy as np
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from desktop_bridge.config import settings
from desktop_bridge.ml.local_analyzer import LocalVibrationAnalyzer

router = APIRouter(prefix="/vibration", tags=["inspection"])

# HTTP client for backend
http_client = httpx.AsyncClient(timeout=settings.backend_timeout)

# Local analyzer (optional, for offline/edge inference)
local_analyzer = None


class VibrationPayload(BaseModel):
    device_id: str
    x: list[float]
    y: list[float]
    z: list[float]
    sample_rate_hz: int = Field(default=1000, ge=100, le=10000)
    method: str = Field(default="auto", pattern="^(auto|cnn|traditional|both)$")


class VibrationResponse(BaseModel):
    inspection_id: str
    status: str
    method: str
    predicted_class: Optional[str] = None
    confidence: Optional[float] = None
    worst_axis: Optional[str] = None
    axis_results: Optional[dict] = None
    metrics: Optional[dict] = None
    model_type: Optional[str] = None
    timestamp: str
    processing_time_ms: float


async def get_http_client() -> httpx.AsyncClient:
    """Dependency for HTTP client."""
    return http_client


@router.post("/analyze", response_model=VibrationResponse)
async def analyze_vibration(
    payload: VibrationPayload,
    client: httpx.AsyncClient = Depends(get_http_client)
):
    """
    Analyze 3-axis vibration data for bearing fault detection.
    
    Methods:
    - "auto": Try local CNN first, fallback to backend, then traditional
    - "cnn": Use local CNN model (if available)
    - "traditional": Use feature extraction + Isolation Forest
    - "both": Return both local CNN and backend results
    """
    start_time = time.time()
    
    # Validate input
    if len(payload.x) != len(payload.y) or len(payload.x) != len(payload.z):
        raise HTTPException(status_code=400, detail="All axes must have same length")
    
    if len(payload.x) < 10:
        raise HTTPException(status_code=400, detail="Signal too short (minimum 10 samples)")
    
    # Convert to numpy
    x = np.array(payload.x, dtype=np.float32)
    y = np.array(payload.y, dtype=np.float32)
    z = np.array(payload.z, dtype=np.float32)
    
    # Determine analysis strategy
    method = payload.method
    result = {}
    
    if payload.method in ("auto", "cnn", "both"):
        # Try local CNN first
        local_result = await analyze_local_cnn(x, y, z, payload.sample_rate_hz)
        if local_result.get("status") != "model_unavailable":
            result = local_result
            method = "cnn"
    
    if payload.method in ("auto", "traditional", "both") and not result:
        # Fallback to traditional
        result = await analyze_traditional(x, y, z, payload.sample_rate_hz)
        method = "traditional"
    
    if payload.method == "both" and "cnn" not in method:
        # Run both and combine
        local_result = await analyze_local_cnn(x, y, z, payload.sample_rate_hz)
        trad_result = await analyze_traditional(x, y, z, payload.sample_rate_hz)
        result = {"local": local_result, "backend": trad_result}
        method = "both"
    
    # Fallback to backend API if local unavailable
    if not result or result.get("status") == "model_unavailable":
        try:
            response = await client.post(
                f"{settings.backend_url}/api/v1/inspect/vibration",
                json=payload.model_dump()
            )
            result = response.json()
            method = f"backend_{payload.method}"
        except Exception as e:
            # Final fallback to traditional
            result = await analyze_traditional(x, y, z, payload.sample_rate_hz)
            method = "traditional_fallback"
    
    processing_time = (time.time() - start_time) * 1000
    
    # Build response
    inspection_id = str(uuid.uuid4())[:8]
    
    return VibrationResponse(
        inspection_id=inspection_id,
        status=result.get("status", "unknown"),
        method=method,
        predicted_class=result.get("predicted_class"),
        confidence=result.get("confidence"),
        worst_axis=result.get("worst_axis"),
        axis_results=result.get("axis_results"),
        metrics=result.get("metrics"),
        model_type=result.get("model_type"),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        processing_time_ms=processing_time
    )


async def analyze_local_cnn(
    x: np.ndarray, 
    y: np.ndarray, 
    z: np.ndarray, 
    fs: int
) -> dict:
    """Analyze using local CNN model."""
    global local_analyzer
    
    if local_analyzer is None:
        from desktop_bridge.ml.local_analyzer import LocalVibrationAnalyzer
        local_analyzer = LocalVibrationAnalyzer()
    
    return await local_analyzer.analyze(x, y, z, fs)


async def analyze_traditional(x: np.ndarray, y: np.ndarray, z: np.ndarray, fs: int) -> dict:
    """Analyze using traditional feature extraction."""
    from desktop_bridge.ml.traditional import analyze_traditional_features
    return await analyze_traditional_features(x, y, z, fs)


@router.post("/cnn")
async def analyze_cnn_only(payload: VibrationPayload):
    """Analyze using CNN model only."""
    import numpy as np
    x = np.array(payload.x, dtype=np.float32)
    y = np.array(payload.y, dtype=np.float32)
    z = np.array(payload.z, dtype=np.float32)
    
    result = await analyze_local_cnn(x, y, z, payload.sample_rate_hz)
    result["inspection_id"] = str(uuid.uuid4())[:8]
    return result


@router.post("/traditional")
async def analyze_traditional_only(payload: VibrationPayload):
    """Analyze using traditional features only."""
    import numpy as np
    x = np.array(payload.x, dtype=np.float32)
    y = np.array(payload.y, dtype=np.float32)
    z = np.array(payload.z, dtype=np.float32)
    
    result = await analyze_traditional(x, y, z, payload.sample_rate_hz)
    result["inspection_id"] = str(uuid.uuid4())[:8]
    return result


@router.get("/methods")
async def list_methods():
    """List available analysis methods."""
    return {
        "methods": [
            {"id": "auto", "name": "Auto", "description": "Try CNN first, fallback to traditional"},
            {"id": "cnn", "name": "CNN", "description": "Local CNN model (edge inference)"},
            {"id": "traditional", "name": "Traditional", "description": "Feature extraction + Isolation Forest"},
            {"id": "both", "name": "Both", "description": "Run both CNN and traditional"}
        ]
    }