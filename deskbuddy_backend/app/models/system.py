"""
System monitoring models (StatNode-inspired).
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Float,
    Integer,
    BigInteger,
    Text,
    ForeignKey,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.types import UUID, JSONB
import uuid
import enum

from app.core.database import Base


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class MetricType(str, enum.Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    GPU = "gpu"
    TEMPERATURE = "temperature"
    CUSTOM = "custom"


class SystemMetrics(Base):
    __tablename__ = "system_metrics"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    
    # CPU metrics
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    cpu_per_core: Mapped[list] = mapped_column(JSONB, default=list)
    cpu_freq_current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpu_freq_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpu_freq_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Memory metrics. Byte counts are BIGINT because 16 GB+ machines and
    # multi-terabyte disks overflow a 32-bit INTEGER.
    memory_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_available_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    swap_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    swap_used_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    swap_total_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Disk metrics
    disk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_free_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_read_bytes_sec: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    disk_write_bytes_sec: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Network metrics
    network_sent_bytes_sec: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    network_recv_bytes_sec: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    network_sent_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    network_recv_total: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # GPU metrics (if available)
    gpu_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_memory_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_memory_used_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    gpu_memory_total_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    gpu_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Temperature
    cpu_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Processes
    process_count: Mapped[int] = mapped_column(Integer, default=0)
    thread_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Boot time
    boot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_system_metrics_timestamp", "timestamp"),
    )
    
    def __repr__(self) -> str:
        return f"<SystemMetrics cpu={self.cpu_percent}% mem={self.memory_percent}%>"


class AlertRule(Base):
    __tablename__ = "alert_rules"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metric_type: Mapped[MetricType] = mapped_column(
        SQLEnum(MetricType), nullable=False
    )
    condition: Mapped[str] = mapped_column(String(50), nullable=False)  # >, <, >=, <=, ==, !=
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        SQLEnum(AlertSeverity), default=AlertSeverity.WARNING
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, default=60)  # How long condition must persist
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)  # Cooldown between alerts
    notification_channels: Mapped[list] = mapped_column(JSONB, default=list)  # email, webhook, push, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<AlertRule {self.name}: {self.metric_type.value} {self.condition} {self.threshold}>"


class Alert(Base):
    __tablename__ = "alerts"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("alert_rules.id"))
    status: Mapped[AlertStatus] = mapped_column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE)
    severity: Mapped[AlertSeverity] = mapped_column(SQLEnum(AlertSeverity), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)  # Value that triggered alert
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    metric_type: Mapped[MetricType] = mapped_column(SQLEnum(MetricType), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    alert_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Relationships
    rule: Mapped["AlertRule"] = relationship("AlertRule")
    
    __table_args__ = (
        Index("ix_alerts_status_started", "status", "started_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Alert {self.id} {self.status} {self.severity}>"


class AlertNotification(Base):
    __tablename__ = "alert_notifications"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("alerts.id"))
    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # email, webhook, push, sms
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    def __repr__(self) -> str:
        return f"<AlertNotification {self.id} for alert {self.alert_id}>"