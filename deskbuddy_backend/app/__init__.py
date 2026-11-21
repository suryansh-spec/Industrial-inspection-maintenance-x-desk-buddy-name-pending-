"""
DeskBuddy Backend - Unified Desktop Companion Backend.

A unified backend inspired by:
- DeskMate: Desktop companion with notifications, Pomodoro, quick actions
- deskey-v2: Keyboard/macro mapping with layers
- Hermes: Multi-channel notification delivery
- StatNode: System monitoring with alerting
- yt-music-companion: YouTube Music integration
"""
from app.core.config import settings
from app.core.database import Base, engine, get_db, init_db
from app.core.events import event_bus, EventBus, Event, EventType
from app.core.security import (
    create_access_token, create_refresh_token, decode_token,
    get_current_user, get_current_active_user, create_token_pair
)
from app.core.events import event_bus, EventBus, Event, EventType

__version__ = "1.0.0"

__all__ = [
    "settings",
    "Base",
    "engine",
    "get_db",
    "init_db",
    "event_bus",
    "EventBus",
    "Event",
    "EventType",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "get_current_active_user",
    "create_token_pair",
]