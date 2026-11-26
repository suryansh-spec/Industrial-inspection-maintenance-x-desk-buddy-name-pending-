"""
Notification models (Hermes-inspired).
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.types import UUID, JSONB
import uuid
import enum

from app.core.database import Base


class NotificationPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DISMISSED = "dismissed"
    FAILED = "failed"


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    PUSH = "push"
    SMS = "sms"
    IN_APP = "in_app"
    WEBSOCKET = "websocket"
    DESKMATE = "deskmate"


class Notification(Base):
    __tablename__ = "notifications"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[NotificationPriority] = mapped_column(
        SQLEnum(NotificationPriority), default=NotificationPriority.NORMAL
    )
    status: Mapped[NotificationStatus] = mapped_column(
        SQLEnum(NotificationStatus), default=NotificationStatus.PENDING
    )
    category: Mapped[str] = mapped_column(String(50), default="general", index=True)
    source: Mapped[str] = mapped_column(String(100), default="system")
    
    # User targeting
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    channels: Mapped[List[NotificationChannel]] = mapped_column(
        JSONB, default=list
    )
    
    # Content
    actions: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    notification_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Status tracking
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="notifications")
    
    # Indexes
    __table_args__ = (
        Index("ix_notifications_user_status", "user_id", "status"),
        Index("ix_notifications_category_created", "category", "created_at"),
        Index("ix_notifications_expires", "expires_at"),
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "status": self.status.value,
            "category": self.category,
            "source": self.source,
            "actions": self.actions,
            "read": self.status == NotificationStatus.READ,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<Notification {self.title} [{self.priority.value}]>"


class NotificationChannelConfig(Base):
    __tablename__ = "notification_channels"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    channel_type: Mapped[NotificationChannel] = mapped_column(
        SQLEnum(NotificationChannel), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # API keys, webhook URLs, etc.
    priority_filter: Mapped[list] = mapped_column(JSONB, default=list)  # Which priorities to send
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<NotificationChannel {self.name} ({self.channel_type.value})>"


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title_template: Mapped[str] = mapped_column(String(255), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    default_priority: Mapped[str] = mapped_column(String(20), default="normal")
    default_category: Mapped[str] = mapped_column(String(50), default="general")
    default_channels: Mapped[list] = mapped_column(JSONB, default=list)
    variables: Mapped[list] = mapped_column(JSONB, default=list)  # Required template variables
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<NotificationTemplate {self.name}>"