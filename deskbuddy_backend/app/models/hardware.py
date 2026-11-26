"""
Hardware models for Arduino/ESP32 device management.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Integer, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.types import UUID, JSONB
import uuid
import enum

from app.core.database import Base


class DeviceType(str, enum.Enum):
    ESP32 = "esp32"
    ESP32_S3 = "esp32_s3"
    ESP8266 = "esp8266"
    ARDUINO = "arduino"
    RASPBERRY_PI = "raspberry_pi"
    GENERIC = "generic"


class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"
    UPDATING = "updating"


class SensorType(str, enum.Enum):
    ACCELEROMETER = "accelerometer"
    GYROSCOPE = "gyroscope"
    MAGNETOMETER = "magnetometer"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    PROXIMITY = "proximity"
    LIGHT = "light"
    SOUND = "sound"
    VOLTAGE = "voltage"
    CURRENT = "current"
    CUSTOM = "custom"


class DeviceMode(str, enum.Enum):
    INSPECTION = "inspection"
    DESK_BUDDY = "desk_buddy"
    MAINTENANCE = "maintenance"
    BOOTLOADER = "bootloader"


class Device(Base):
    __tablename__ = "devices"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    device_type: Mapped[DeviceType] = mapped_column(SQLEnum(DeviceType), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(SQLEnum(DeviceStatus), default=DeviceStatus.OFFLINE)
    mode: Mapped[DeviceMode] = mapped_column(SQLEnum(DeviceMode), default=DeviceMode.DESK_BUDDY)
    
    # Connection info
    serial_port: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv4 or IPv6
    mac_address: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    port: Mapped[int] = mapped_column(Integer, default=80)
    
    # Identification
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hardware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    
    # Capabilities
    capabilities: Mapped[list] = mapped_column(JSONB, default=list)  # ["accelerometer", "bme280", "oled", "tft", "speaker", "mic"]
    supported_modes: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Configuration
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Status
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    free_heap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    sensors: Mapped[List["Sensor"]] = relationship("Sensor", back_populates="device", cascade="all, delete-orphan")
    inspections: Mapped[List["InspectionSession"]] = relationship("InspectionSession", back_populates="device", cascade="all, delete-orphan")
    sensor_readings: Mapped[List["SensorReading"]] = relationship("SensorReading", back_populates="device", cascade="all, delete-orphan")
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    last_config_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("ix_devices_status_last_seen", "status", "last_seen"),
    )
    
    def __repr__(self) -> str:
        return f"<Device {self.name} ({self.device_type.value})>"


class Sensor(Base):
    __tablename__ = "sensors"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sensor_type: Mapped[SensorType] = mapped_column(SQLEnum(SensorType), nullable=False)
    
    # Configuration
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # "m/s²", "°C", "%", "hPa", etc.
    min_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    precision: Mapped[int] = mapped_column(Integer, default=2)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, default=100)
    
    # Calibration
    calibration_offset: Mapped[float] = mapped_column(Float, default=0.0)
    calibration_scale: Mapped[float] = mapped_column(Float, default=1.0)
    
    # Thresholds for alerts
    warning_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    warning_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    critical_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    critical_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_reading: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_reading_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="sensors")
    readings: Mapped[List["SensorReading"]] = relationship("SensorReading", back_populates="sensor", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Sensor {self.name} ({self.sensor_type.value})>"


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id"))
    inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_sessions.id"), nullable=True, index=True
    )
    
    value: Mapped[float] = mapped_column(Float, nullable=False)
    raw_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality: Mapped[int] = mapped_column(Integer, default=100)  # 0-100 quality score
    
    # Context
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    sample_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Position in batch
    
    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="sensor_readings")
    sensor: Mapped["Sensor"] = relationship("Sensor", back_populates="readings")
    inspection: Mapped[Optional["InspectionSession"]] = relationship(
        "InspectionSession", back_populates="sensor_readings"
    )
    
    __table_args__ = (
        Index("ix_sensor_readings_device_timestamp", "device_id", "timestamp"),
        Index("ix_sensor_readings_sensor_timestamp", "sensor_id", "timestamp"),
    )
    
    def __repr__(self) -> str:
        return f"<SensorReading {self.value} {self.timestamp}>"


class InspectionSession(Base):
    __tablename__ = "inspection_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"))
    session_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    
    # Configuration
    method: Mapped[str] = mapped_column(String(50), default="auto")  # auto, cnn, traditional, both
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)  # pending, running, completed, failed
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    
    # Results
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_class: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="inspections")
    sensor_readings: Mapped[List["SensorReading"]] = relationship("SensorReading", back_populates="inspection", cascade="all, delete-orphan")
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_inspections_device_status", "device_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<InspectionSession {self.session_id} [{self.status}]>"