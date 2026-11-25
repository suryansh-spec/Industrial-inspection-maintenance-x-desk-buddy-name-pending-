"""
DeskMate service - lightweight desktop companion state.

Holds in-memory notifications and Pomodoro state that both the REST API and
the WebSocket layer can share. Replaces the previous dependency on the
standalone ``desktop_bridge`` package.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeskNotification:
    """A single in-app notification."""

    title: str
    message: str
    type: str = "info"
    actions: List[Dict[str, str]] = field(default_factory=list)
    read: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "actions": self.actions,
            "read": self.read,
            "timestamp": self.timestamp.isoformat(),
        }


class DeskMateService:
    """In-memory state for notifications, Pomodoro and quick actions."""

    def __init__(self, max_notifications: int = 200):
        self.max_notifications = max_notifications
        self._notifications: List[DeskNotification] = []
        self._dismissed: set[str] = set()

        # Pomodoro state
        self.pomodoro_running = False
        self.pomodoro_duration_seconds = 25 * 60
        self.pomodoro_started_at: Optional[float] = None
        self.pomodoro_is_break = False

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    def add_notification(
        self,
        title: str,
        message: str,
        type: str = "info",
        actions: Optional[List[Dict[str, str]]] = None,
    ) -> DeskNotification:
        notification = DeskNotification(
            title=title,
            message=message,
            type=type,
            actions=actions or [],
        )
        self._notifications.insert(0, notification)
        if len(self._notifications) > self.max_notifications:
            self._notifications = self._notifications[: self.max_notifications]
        return notification

    def get_notifications(
        self,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[DeskNotification]:
        notifications = [
            n for n in self._notifications if n.id not in self._dismissed
        ]
        if unread_only:
            notifications = [n for n in notifications if not n.read]
        return notifications[: max(0, limit)]

    def get_unread_count(self) -> int:
        return sum(
            1
            for n in self._notifications
            if not n.read and n.id not in self._dismissed
        )

    def mark_read(self, notification_id: str) -> bool:
        for notification in self._notifications:
            if notification.id == notification_id:
                notification.read = True
                return True
        return False

    def dismiss(self, notification_id: str) -> bool:
        for notification in self._notifications:
            if notification.id == notification_id:
                self._dismissed.add(notification_id)
                return True
        return False

    def clear_notifications(self) -> None:
        self._notifications.clear()
        self._dismissed.clear()

    # ------------------------------------------------------------------
    # Pomodoro
    # ------------------------------------------------------------------
    def start_pomodoro(self, minutes: int = 25) -> Dict[str, Any]:
        self.pomodoro_duration_seconds = max(1, minutes) * 60
        self.pomodoro_started_at = time.monotonic()
        self.pomodoro_running = True
        self.pomodoro_is_break = False
        return self.get_pomodoro_status()

    def pause_pomodoro(self) -> Dict[str, Any]:
        if self.pomodoro_running and self.pomodoro_started_at is not None:
            elapsed = time.monotonic() - self.pomodoro_started_at
            self.pomodoro_duration_seconds = max(0, int(self.pomodoro_duration_seconds - elapsed))
        self.pomodoro_started_at = None
        self.pomodoro_running = False
        return self.get_pomodoro_status()

    def reset_pomodoro(self, minutes: int = 25) -> Dict[str, Any]:
        self.pomodoro_duration_seconds = max(1, minutes) * 60
        self.pomodoro_started_at = None
        self.pomodoro_running = False
        self.pomodoro_is_break = False
        return self.get_pomodoro_status()

    def get_pomodoro_status(self) -> Dict[str, Any]:
        remaining = self.pomodoro_duration_seconds
        if self.pomodoro_running and self.pomodoro_started_at is not None:
            elapsed = time.monotonic() - self.pomodoro_started_at
            remaining = max(0, int(self.pomodoro_duration_seconds - elapsed))
        return {
            "running": self.pomodoro_running,
            "is_break": self.pomodoro_is_break,
            "duration_seconds": self.pomodoro_duration_seconds,
            "remaining_seconds": remaining,
        }


deskmate_service = DeskMateService()


def create_deskbuddy_services() -> Dict[str, Any]:
    """Return the shared service instances used by the application."""
    from app.services.system_monitor import system_monitor
    from app.services.notification_service import notification_service
    from app.services.music import music_controller
    from app.services.calendar import calendar_service
    from app.services.hardware_bridge import hardware_bridge
    from app.services.voice import voice_assistant

    return {
        "system_monitor": system_monitor,
        "notification_service": notification_service,
        "music_controller": music_controller,
        "calendar_service": calendar_service,
        "hardware_bridge": hardware_bridge,
        "voice_assistant": voice_assistant,
        "deskmate_service": deskmate_service,
    }
