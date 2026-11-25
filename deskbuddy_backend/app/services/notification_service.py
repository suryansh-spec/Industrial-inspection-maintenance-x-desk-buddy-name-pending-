"""
Notification Service (Hermes-inspired).
Multi-channel notification delivery with persistence, retries, and templates.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import json

import apprise
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.events import event_bus, EventType, Event
from app.models.notifications import (
    Notification, NotificationChannel, NotificationPriority,
    NotificationStatus, NotificationChannelConfig, NotificationTemplate
)
from app.models.user import User
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Multi-channel notification service inspired by Hermes.
    Supports: Email, Webhook, Push, SMS, In-App, WebSocket, Desktop (DeskMate)
    """
    
    def __init__(self):
        self.apprise = apprise.Apprise()
        self._channel_configs: Dict[str, dict] = {}
        self._templates: Dict[str, dict] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize notification channels."""
        if self._initialized:
            return
        
        # Load channel configs from database
        await self._load_channel_configs()
        await self._load_templates()
        
        # Configure Apprise with available services
        await self._configure_apprise()
        
        self._initialized = True
        logger.info("Notification service initialized")
    
    async def _load_channel_configs(self):
        """Load channel configurations from database."""
        async with async_session_maker() as db:
            from app.models.notifications import NotificationChannelConfig
            result = await db.execute(
                select(NotificationChannelConfig).where(NotificationChannelConfig.is_active == True)
            )
            for config in result.scalars().all():
                self._channel_configs[config.channel_type.value] = config.config
    
    async def _load_templates(self):
        """Load notification templates."""
        async with async_session_maker() as db:
            from app.models.notifications import NotificationTemplate
            result = await db.execute(
                select(NotificationTemplate).where(NotificationTemplate.is_active == True)
            )
            for template in result.scalars().all():
                self._templates[template.name] = {
                    "title": template.title_template,
                    "message": template.message_template,
                    "priority": template.default_priority,
                    "category": template.default_category,
                    "channels": template.default_channels,
                    "variables": template.variables
                }
    
    async def _configure_apprise(self):
        """Configure Apprise with available services."""
        # Add email if configured
        if "email" in self._channel_configs:
            cfg = self._channel_configs["email"]
            self.apprise.add(f"mailto://{cfg.get('username')}:{cfg.get('password')}@{cfg.get('server')}:{cfg.get('port')}")
        
        # Add webhook if configured
        if "webhook" in self._channel_configs:
            cfg = self._channel_configs["webhook"]
            self.apprise.add(f"webhook://{cfg.get('url')}")
        
        # Add push services
        if "pushover" in self._channel_configs:
            cfg = self._channel_configs["pushover"]
            self.apprise.add(f"pover://{cfg.get('user_key')}@{cfg.get('api_token')}")
        
        if "pushbullet" in self._channel_configs:
            cfg = self._channel_configs["pushbullet"]
            self.apprise.add(f"pbul://{cfg.get('access_token')}")
        
        # Add Discord webhook
        if "discord" in self._channel_configs:
            cfg = self._channel_configs["discord"]
            self.apprise.add(f"discord://{cfg.get('webhook_id')}/{cfg.get('webhook_token')}")
        
        # Add Slack
        if "slack" in self._channel_configs:
            cfg = self._channel_configs["slack"]
            self.apprise.add(f"slack://{cfg.get('token')}/{cfg.get('channel')}")
    
    async def send_notification(
        self,
        title: str,
        message: str,
        priority: str = "normal",
        category: str = "general",
        user_id: Optional[str] = None,
        channels: Optional[List[str]] = None,
        actions: Optional[List[dict]] = None,
        metadata: Optional[dict] = None,
        template: Optional[str] = None,
        template_vars: Optional[dict] = None,
        expires_in: Optional[int] = None
    ) -> str:
        """
        Send a notification through configured channels.
        
        Args:
            title: Notification title
            message: Notification message
            priority: low, normal, high, urgent
            category: Notification category
            user_id: Target user ID (optional, None = broadcast)
            channels: Specific channels to use (None = all enabled)
            actions: Action buttons for interactive notifications
            metadata: Additional metadata
            template: Template name to use
            template_vars: Variables for template rendering
            expires_in: Expiration in seconds
        
        Returns:
            Notification ID
        """
        if not self._initialized:
            await self.initialize()
        
        notification_id = str(uuid.uuid4())
        
        # Resolve template if provided
        if template and template in self._templates:
            tpl = self._templates[template]
            if template_vars:
                title = title.format(**template_vars) if "{" in title else title
                message = message.format(**template_vars) if "{" in message else message
            else:
                title = title or tpl.get("title", "")
                message = message or tpl.get("message", "")
                priority = priority or tpl.get("priority", "normal")
                category = category or tpl.get("category", "general")
        
        # Create notification record
        notification = {
            "id": notification_id,
            "title": title,
            "message": message,
            "priority": priority,
            "status": "pending",
            "category": category,
            "source": "api",
            "user_id": user_id,
            "channels": channels or ["websocket", "in_app"],
            "actions": actions or [],
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() if expires_in else None
        }
        
        # Persist to database
        await self._persist_notification(notification)
        
        # Send via Apprise (email, webhook, push, etc.)
        if channels is None or "email" in channels or "webhook" in channels or "pushover" in channels:
            task = asyncio.create_task(self._send_via_apprise(notification))
            if not hasattr(self, "_bg_tasks"):
                self._bg_tasks = set()
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        
        # Send via WebSocket for real-time
        from app.core.events import event_bus, EventType, Event
        await event_bus.publish(Event(
            type=EventType.NOTIFICATION_CREATED,
            data={
                "notification": {
                    "id": notification_id,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "category": category,
                    "timestamp": datetime.utcnow().isoformat(),
                    "actions": actions or []
                }
            }, source="notification_service")
        )
        
        return notification_id
    
    async def _send_via_apprise(self, notification: dict):
        """Send notification via Apprise (email, webhook, push, etc.)."""
        try:
            body = f"{notification['title']}\n\n{notification['message']}"
            
            # Add actions as markdown
            if notification.get("actions"):
                body += "\n\n**Actions:**\n"
                for action in notification["actions"]:
                    body += f"- {action.get('label', 'Action')}: {action.get('action', '')}\n"
            
            notify_type_map = {
                "low": "info",
                "normal": "info",
                "high": "warning",
                "urgent": "failure",
            }
            apprise_type = notify_type_map.get(str(notification.get("priority", "normal")).lower(), "info")

            # Send via Apprise
            await asyncio.to_thread(
                self.apprise.notify,
                body=body,
                title=notification["title"],
                notify_type=apprise_type,
            )
            
            # Update status
            await self._update_notification_status(notification["id"], "sent")
        except Exception as e:
            logger.error(f"Apprise notification failed: {e}")
            await self._update_notification_status(notification["id"], "failed")
    
    async def _send_websocket(self, notification: dict):
        """Send notification via WebSocket to connected clients."""
        from app.main import ws_manager
        from app.core.events import event_bus, EventType, Event
        
        await event_bus.publish(Event(
            type=EventType.NOTIFICATION_CREATED,
            data={
                "notification": {
                    "id": notification["id"],
                    "title": notification["title"],
                    "message": notification["message"],
                    "priority": notification["priority"],
                    "category": notification["category"],
                    "timestamp": datetime.utcnow().isoformat(),
                    "actions": notification.get("actions", [])
                }
            },
            source="notification_service",
        ))
    
    async def _persist_notification(self, notification: dict):
        """Persist notification to database."""
        async with async_session_maker() as db:
            from app.models.notifications import Notification, NotificationPriority, NotificationStatus
            from app.models.user import User
            
            user_id = None
            if notification.get("user_id"):
                from uuid import UUID
                user_id = UUID(notification["user_id"])
            
            notification_obj = Notification(
                id=uuid.UUID(notification["id"]),
                title=notification["title"],
                message=notification["message"],
                priority=NotificationPriority(notification["priority"]),
                status=NotificationStatus(notification["status"]),
                category=notification["category"],
                source=notification["source"],
                user_id=user_id,
                channels=notification.get("channels", []),
                actions=notification.get("actions", []),
                notification_metadata=notification.get("metadata", {}),
                expires_at=datetime.fromisoformat(notification["expires_at"]) if notification.get("expires_at") else None
            )
            
            db.add(notification_obj)
            await db.commit()
    
    async def _update_notification_status(self, notification_id: str, status: str):
        """Update notification status in database."""
        async with async_session_maker() as db:
            from app.models.notifications import Notification, NotificationStatus
            from uuid import UUID
            
            result = await db.execute(
                select(Notification).where(Notification.id == UUID(notification_id))
            )
            notif = result.scalar_one_or_none()
            if notif:
                notif.status = NotificationStatus(status)
                if status == "sent":
                    notif.sent_at = datetime.utcnow()
                elif status == "delivered":
                    notif.delivered_at = datetime.utcnow()
                elif status == "read":
                    notif.read_at = datetime.utcnow()
                    notif.status = NotificationStatus.READ
                elif status == "dismissed":
                    notif.dismissed_at = datetime.utcnow()
                    notif.status = NotificationStatus.DISMISSED
                await db.commit()
    
    async def mark_read(self, notification_id: str, user_id: str) -> bool:
        """Mark notification as read."""
        async with async_session_maker() as db:
            from app.models.notifications import Notification, NotificationStatus
            from uuid import UUID
            
            result = await db.execute(
                select(Notification).where(
                    Notification.id == UUID(notification_id),
                    Notification.user_id == UUID(user_id)
                )
            )
            notif = result.scalar_one_or_none()
            if notif:
                notif.status = NotificationStatus.READ
                notif.read_at = datetime.utcnow()
                await db.commit()
                return True
        return False
    
    async def dismiss(self, notification_id: str, user_id: str) -> bool:
        """Dismiss a notification."""
        async with async_session_maker() as db:
            from app.models.notifications import Notification, NotificationStatus
            from uuid import UUID
            
            result = await db.execute(
                select(Notification).where(
                    Notification.id == UUID(notification_id),
                    Notification.user_id == UUID(user_id)
                )
            )
            notif = result.scalar_one_or_none()
            if notif:
                notif.status = NotificationStatus.DISMISSED
                notif.dismissed_at = datetime.utcnow()
                await db.commit()
                return True
        return False
    
    async def get_notifications(
        self,
        user_id: Optional[str] = None,
        unread_only: bool = False,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """Get notifications with filtering."""
        async with async_session_maker() as db:
            from app.models.notifications import Notification, NotificationStatus
            from uuid import UUID
            
            query = select(Notification)
            
            if user_id:
                query = query.where(Notification.user_id == UUID(user_id))
            if unread_only:
                query = query.where(Notification.status != NotificationStatus.READ)
            if category:
                query = query.where(Notification.category == category)
            
            query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
            result = await db.execute(query)
            notifications = result.scalars().all()
            
            return [n.to_dict() for n in notifications]
    
    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications."""
        async with async_session_maker() as db:
            from app.models.notifications import Notification, NotificationStatus
            from uuid import UUID
            
            result = await db.execute(
                select(Notification).where(
                    Notification.user_id == UUID(user_id),
                    Notification.status != NotificationStatus.READ
                )
            )
            return len(result.scalars().all())
    
    async def send_template_notification(
        self,
        template_name: str,
        template_vars: dict,
        user_id: Optional[str] = None,
        channels: Optional[List[str]] = None
    ) -> str:
        """Send notification using a template."""
        async with async_session_maker() as db:
            from app.models.notifications import NotificationTemplate
            from uuid import UUID
            
            result = await db.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.name == template_name,
                    NotificationTemplate.is_active == True
                )
            )
            template = result.scalar_one_or_none()
            
            if not template:
                raise ValueError(f"Template '{template_name}' not found")
            
            # Validate required variables
            missing = set(template.variables) - set(template_vars.keys())
            if missing:
                raise ValueError(f"Missing template variables: {missing}")
            
            # Render template
            title = template.title_template.format(**template_vars)
            message = template.message_template.format(**template_vars)
            
            return await self.send_notification(
                title=title,
                message=message,
                priority=template.default_priority,
                category=template.default_category,
                user_id=user_id,
                channels=channels or template.default_channels
            )


# Global instance
notification_service = NotificationService()