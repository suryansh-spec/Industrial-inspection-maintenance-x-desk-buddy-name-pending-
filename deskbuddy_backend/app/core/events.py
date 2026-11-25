"""
Event system for inter-service communication.
"""
import asyncio
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class EventType(Enum):
    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    
    # Device events
    DEVICE_CONNECTED = "device.connected"
    DEVICE_DISCONNECTED = "device.disconnected"
    DEVICE_MODE_CHANGED = "device.mode_changed"
    DEVICE_SENSOR_DATA = "device.sensor_data"
    
    # Inspection events
    INSPECTION_STARTED = "inspection.started"
    INSPECTION_COMPLETED = "inspection.completed"
    INSPECTION_FAILED = "inspection.failed"
    
    # Notification events
    NOTIFICATION_CREATED = "notification.created"
    NOTIFICATION_READ = "notification.read"
    NOTIFICATION_DISMISSED = "notification.dismissed"
    
    # PC Monitoring events
    PC_METRICS_UPDATED = "pc.metrics_updated"
    PC_ALERT_TRIGGERED = "pc.alert_triggered"
    
    # Media events
    MEDIA_PLAYBACK_CHANGED = "media.playback_changed"
    MEDIA_TRACK_CHANGED = "media.track_changed"
    MEDIA_VOLUME_CHANGED = "media.volume_changed"
    
    # Calendar events
    CALENDAR_EVENT_CREATED = "calendar.event_created"
    CALENDAR_EVENT_UPDATED = "calendar.event_updated"
    CALENDAR_EVENT_REMINDER = "calendar.event_reminder"
    
    # Keyboard/Deskey events
    KEY_PRESSED = "keyboard.key_pressed"
    MACRO_TRIGGERED = "keyboard.macro_triggered"
    LAYER_CHANGED = "keyboard.layer_changed"
    
    # Pomodoro events
    POMODORO_STARTED = "pomodoro.started"
    POMODORO_PAUSED = "pomodoro.paused"
    POMODORO_COMPLETED = "pomodoro.completed"
    POMODORO_TICK = "pomodoro.tick"
    
    # Clipboard events
    CLIPBOARD_CHANGED = "clipboard.changed"
    
    # Voice Assistant
    VOICE_QUERY = "voice.query"
    VOICE_RESPONSE = "voice.response"
    VOICE_TOOL_CALLED = "voice.tool_called"


@dataclass
class Event:
    """Event data structure."""
    type: EventType
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventBus:
    """Async event bus for inter-service communication."""
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._wildcard_subscribers: List[Callable] = []
        self._lock = asyncio.Lock()
        self._event_history: List[Event] = []
        self._max_history = 1000
    
    async def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """Subscribe to an event type."""
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
    
    async def subscribe_all(self, handler: Callable) -> None:
        """Subscribe to all events."""
        async with self._lock:
            self._wildcard_subscribers.append(handler)
    
    async def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """Unsubscribe from an event type."""
        async with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass
    
    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]
        
        # Call specific subscribers
        handlers = self._subscribers.get(event.type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.type}: {e}")
        
        # Call wildcard subscribers
        for handler in self._wildcard_subscribers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in wildcard handler: {e}")
    
    async def publish_sync(self, event_type: EventType, data: dict, source: str = "") -> None:
        """Convenience method to publish an event."""
        event = Event(
            type=event_type,
            data=data,
            source=source,
        )
        await self.publish(event)
    
    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """Get event history."""
        if event_type:
            return [e for e in self._event_history if e.type == event_type][-100:]
        return self._event_history[-100:]


# Global event bus instance
event_bus = EventBus()


# Convenience functions for common events
async def emit_device_connected(port: str, device_info: dict):
    await event_bus.publish(Event(
        type=EventType.DEVICE_CONNECTED,
        data={"port": port, "device_info": device_info},
        source="hardware_bridge"
    ))


async def emit_device_disconnected(port: str):
    await event_bus.publish(Event(
        type=EventType.DEVICE_DISCONNECTED,
        data={"port": ""},
        source="hardware_bridge"
    ))


async def emit_sensor_data(sensor_data: dict):
    await event_bus.publish(Event(
        type=EventType.DEVICE_SENSOR_DATA,
        data=sensor_data,
        source="hardware_bridge"
    ))


async def emit_notification(title: str, message: str, priority: str = "normal", category: str = "general"):
    from app.models.notifications import NotificationPriority
    from app.services.notification_service import notification_service
    
    priority_map = {
        "low": NotificationPriority.LOW,
        "normal": NotificationPriority.NORMAL,
        "high": NotificationPriority.HIGH,
        "urgent": NotificationPriority.URGENT
    }
    
    await notification_service.add_notification(
        title=title,
        message=message,
        priority=NotificationPriority(priority),
        category=category
    )


async def emit_pomodoro_tick(remaining: int, is_break: bool):
    from app.services.deskmate import deskmate_service

    if deskmate_service:
        await deskmate_service.on_pomodoro_tick(remaining, is_break)


async def emit_pomodoro_event(event: str):
    from app.services.deskmate import deskmate_service

    if deskmate_service:
        await deskmate_service.on_pomodoro_complete(event)