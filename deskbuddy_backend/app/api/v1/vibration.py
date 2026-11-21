"""
Vibration Analysis API endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
import numpy as np
import uuid
import time

from app.core.config import settings
from app.services.vibration import analyze, local_analyzer

router = APIRouter(prefix="/inspect", tags=["inspection"])


class InspectionRequest(BaseModel):
    device_id: str
    x: List[float]
    y: List[float]
    z: List[float]
    sample_rate_hz: int = Field(default=1000, ge=100, le=10000)
    method: Literal["auto", "cnn", "traditional", "both"] = "auto"
    duration_seconds: int = Field(default=5, ge=1, le=60)


class InspectionResponse(BaseModel):
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


@router.post("/vibration", response_model=InspectionResponse)
async def analyze_vibration_endpoint(payload: InspectionRequest):
    """
    Analyze 3-axis vibration data for bearing fault detection.
    
    Methods:
    - "auto": Try CNN first, fallback to traditional (default)
    - "cnn": Use trained CNN model
    - "traditional": Use feature extraction + Isolation Forest
    - "both": Return both CNN and traditional results
    """
    start_time = time.time()
    
    # Validate input
    if len(payload.x) != len(payload.y) or len(payload.x) != len(payload.z):
        raise HTTPException(status_code=400, detail="All axes must have same length")
    
    if len(payload.x) < 3:
        raise HTTPException(status_code=400, detail="Signal too short (minimum 3 samples)")
    
    # Convert to numpy arrays
    x = np.array(payload.x, dtype=np.float32)
    y = np.array(payload.y, dtype=np.float32)
    z = np.array(payload.z, dtype=np.float32)
    
    # Run analysis
    result = await analyze(x, y, z, payload.sample_rate_hz, payload.method)
    
    processing_time = (time.time() - start_time) * 1000
    
    return InspectionResponse(
        inspection_id=str(uuid.uuid4())[:8],
        status=result.get("status", "unknown"),
        method=payload.method,
        predicted_class=result.get("predicted_class"),
        confidence=result.get("confidence"),
        worst_axis=result.get("worst_axis"),
        axis_results=result.get("axis_results"),
        metrics=result.get("metrics"),
        model_type=result.get("model_type"),
        timestamp=datetime.utcnow().isoformat(),
        processing_time_ms=processing_time
    )


@router.post("/vibration/upload")
async def analyze_vibration_upload(
    file: UploadFile = File(...),
    method: str = Form(default="auto"),
    sample_rate_hz: int = Form(default=1000)
):
    """Analyze vibration from uploaded CSV/JSON file."""
    import pandas as pd
    import io
    
    content = await file.read()
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
            x = df['x'].values.astype(np.float32)
            y = df['y'].values.astype(np.float32)
            z = df['z'].values.astype(np.float32)
        elif file.filename.endswith('.json'):
            import json
            data = json.loads(content)
            x = np.array(data['x'], dtype=np.float32)
            y = np.array(data['y'], dtype=np.float32)
            z = np.array(data['z'], dtype=np.float32)
        else:
            raise HTTPException(400, "Unsupported file format. Use CSV or JSON.")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}")
    
    result = await analyze(x, y, z, sample_rate_hz, method)
    
    return {
        "inspection_id": str(uuid.uuid4())[:8],
        "status": result.get("status"),
        "method": method,
        "predicted_class": result.get("predicted_class"),
        "confidence": result.get("confidence"),
        "worst_axis": result.get("worst_axis"),
        "axis_results": result.get("axis_results"),
        "metrics": result.get("metrics"),
        "model_type": result.get("model_type")
    }


@router.get("/methods")
async def list_inspection_methods():
    """List available inspection methods."""
    return {
        "methods": [
            {"id": "auto", "name": "Auto", "description": "Try CNN first, fallback to traditional"},
            {"id": "cnn", "name": "CNN", "description": "Trained CNN model for bearing fault classification"},
            {"id": "traditional", "name": "Traditional", "description": "Feature extraction + Isolation Forest"},
            {"id": "both", "name": "Both", "description": "Run both CNN and traditional analysis"}
        ]
    }


@router.get("/model/info")
async def get_model_info():
    """Get information about the loaded ML model."""
    if local_analyzer.is_ready():
        return {
            "loaded": True,
            "classes": ["Normal", "Inner Race", "Ball", "Outer Race"],
            "window_size": local_analyzer.window_size,
            "sampling_rate": local_analyzer.sampling_rate,
            "device": str(local_analyzer.device)
        }
    return {"loaded": False}


@router.get("/prognostics/{motor_id}")
async def get_equipment_prognostics(motor_id: str):
    """Get Equipment Age, Health Index, and Predicted Failure Timeline (RUL)."""
    from app.services.prognostics import prognostics_engine
    return prognostics_engine.calculate_rul(motor_id)


@router.post("/prognostics/{motor_id}/update")
async def update_equipment_prognostics(
    motor_id: str,
    rms_mm_s: float,
    diagnosis: str = "Normal Baseline",
    confidence: float = 0.95
):
    """Update equipment live vibration readings and recompute breakdown timeline."""
    from app.services.prognostics import prognostics_engine
    prognostics_engine.update_telemetry(motor_id, rms_mm_s, diagnosis, confidence)
    return prognostics_engine.calculate_rul(motor_id)
