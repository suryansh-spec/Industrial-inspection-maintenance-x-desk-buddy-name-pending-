"""
System metrics API endpoints (StatNode-inspired).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.database import get_db
from app.models.system import SystemMetrics, AlertRule, Alert, AlertSeverity, AlertStatus, MetricType
from app.services.system_monitor import system_monitor
from pydantic import BaseModel

router = APIRouter(prefix="/system", tags=["system"])


# Pydantic models
class SystemMetricsResponse(BaseModel):
    timestamp: datetime
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
    disk_read_mb_s: float
    disk_write_mb_s: float
    network_sent_mb_s: float
    network_recv_mb_s: float
    network_sent_total_mb: float = 0.0
    network_recv_total_mb: float = 0.0
    cpu_temp_c: Optional[float] = None
    cpu_temp_source: Optional[str] = None
    thermal_zone_c: Optional[float] = None
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None
    gpu_memory_used_mb: Optional[int] = None
    gpu_memory_total_mb: Optional[int] = None
    gpu_temp_c: Optional[float] = None
    gpu_fan_percent: Optional[float] = None
    gpu_name: Optional[str] = None
    gpu_source: Optional[str] = None
    process_count: int
    thread_count: int
    boot_time: Optional[datetime] = None
    top_processes: List[dict] = []


class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    metric_type: MetricType
    condition: str  # >, <, >=, <=, ==, !=
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    duration_seconds: int = 60
    cooldown_seconds: int = 300
    notification_channels: List[str] = []


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    metric_type: MetricType
    condition: str
    threshold: float
    severity: AlertSeverity
    duration_seconds: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AlertResponse(BaseModel):
    id: str
    rule_id: str
    status: str
    severity: str
    message: str
    value: float
    threshold: float
    metric_type: str
    started_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_current_metrics():
    """Get current system metrics."""
    metrics = system_monitor.get_metrics()
    if not metrics:
        raise HTTPException(status_code=503, detail="Metrics not available yet")
    return metrics


@router.get("/metrics/history")
async def get_metrics_history(
    duration_minutes: int = Query(default=60, ge=1, le=1440),
    db: AsyncSession = Depends(get_db)
):
    """Get historical metrics."""
    cutoff = datetime.utcnow() - timedelta(minutes=duration_minutes)
    result = await db.execute(
        select(SystemMetrics)
        .where(SystemMetrics.timestamp >= cutoff)
        .order_by(desc(SystemMetrics.timestamp))
        .limit(200)
    )
    metrics = result.scalars().all()
    return [
        {
            "timestamp": m.timestamp.isoformat(),
            "cpu_percent": m.cpu_percent,
            "memory_percent": m.memory_percent,
            "disk_percent": m.disk_percent,
            "cpu_temp_c": m.cpu_temp_c,
            "gpu_percent": m.gpu_percent,
            "gpu_temp_c": m.gpu_temp_c,
        }
        for m in metrics
    ]


@router.get("/metrics/average")
async def get_average_metrics(
    duration_minutes: int = Query(default=5, ge=1, le=60)
):
    """Get average metrics over duration."""
    return {
        "cpu_percent": system_monitor.get_average_cpu(duration_minutes),
        "duration_minutes": duration_minutes
    }


@router.get("/alerts/status")
async def get_alert_status():
    """Get current alert status."""
    return system_monitor.get_alert_status()


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get alerts with optional filtering."""
    query = select(Alert).order_by(desc(Alert.started_at)).limit(limit)
    
    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    return [
        AlertResponse(
            id=str(a.id),
            rule_id=str(a.rule_id),
            status=a.status.value,
            severity=a.severity.value,
            message=a.message,
            value=a.value,
            threshold=a.threshold,
            metric_type=a.metric_type.value,
            started_at=a.started_at,
            acknowledged_at=a.acknowledged_at,
            resolved_at=a.resolved_at
        )
        for a in alerts
    ]


@router.post("/alerts/rules", response_model=AlertRuleResponse)
async def create_alert_rule(
    rule: AlertRuleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new alert rule."""
    from app.models.system import AlertRule
    rule_obj = AlertRule(**rule.model_dump())
    db.add(rule_obj)
    await db.commit()
    await db.refresh(rule_obj)
    
    # Refresh alert rules cache
    from app.services.system_monitor import system_monitor
    await system_monitor._refresh_alert_rules()
    
    return AlertRuleResponse(
        id=str(rule_obj.id),
        name=rule_obj.name,
        description=rule_obj.description,
        metric_type=rule_obj.metric_type,
        condition=rule_obj.condition,
        threshold=rule_obj.threshold,
        severity=rule_obj.severity,
        duration_seconds=rule_obj.duration_seconds,
        is_active=rule_obj.is_active,
        created_at=rule_obj.created_at,
        updated_at=rule_obj.updated_at
    )


@router.get("/alerts/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(db: AsyncSession = Depends(get_db)):
    """List all alert rules."""
    from app.models.system import AlertRule
    result = await db.execute(select(AlertRule).order_by(AlertRule.created_at.desc()))
    rules = result.scalars().all()
    return [
        AlertRuleResponse(
            id=str(r.id),
            name=r.name,
            description=r.description,
            metric_type=r.metric_type,
            condition=r.condition,
            threshold=r.threshold,
            severity=r.severity,
            duration_seconds=r.duration_seconds,
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at
        )
        for r in rules
    ]


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an alert rule."""
    from app.models.system import AlertRule
    from uuid import UUID
    
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == UUID(rule_id))
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    await db.delete(rule)
    await db.commit()
    
    # Refresh cache
    from app.services.system_monitor import system_monitor
    await system_monitor._refresh_alert_rules()
    
    return {"status": "deleted"}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Acknowledge an alert."""
    from app.models.system import Alert, AlertStatus
    from uuid import UUID
    
    result = await db.execute(select(Alert).where(Alert.id == UUID(alert_id)))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    await db.commit()
    return {"status": "acknowledged"}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Resolve an alert."""
    from app.models.system import Alert, AlertStatus
    from uuid import UUID
    
    result = await db.execute(select(Alert).where(Alert.id == UUID(alert_id)))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    return {"status": "resolved"}