"""Central state store with change notifications."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StateManager:
    """Central state store with change notifications."""

    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any, source: str = "core"):
        """Set a state value and notify listeners."""
        async with self._lock:
            old_value = self._state.get(key)
            self._state[key] = value

        # Notify listeners
        for listener in self._listeners.get(key, []):
            try:
                await listener(key, old_value, value, source)
            except Exception as e:
                logger.error(f"State listener error: {e}")

        # Also notify wildcard listeners
        for listener in self._listeners.get("*", []):
            try:
                await listener(key, old_value, value, source)
            except Exception as e:
                logger.error(f"State wildcard listener error: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a state value."""
        return self._state.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Get all state values."""
        return dict(self._state)

    def subscribe(self, key: str, listener: Callable):
        """Subscribe to changes for a specific key (or '*' for all)."""
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(listener)

    async def bulk_set(self, values: Dict[str, Any], source: str = "core"):
        """Set multiple values atomically."""
        async with self._lock:
            for key, value in values.items():
                old_value = self._state.get(key)
                self._state[key] = value
                for listener in self._listeners.get(key, []):
                    try:
                        await listener(key, old_value, value, source)
                    except Exception as e:
                        logger.error(f"State listener error: {e}")


state_manager = StateManager()