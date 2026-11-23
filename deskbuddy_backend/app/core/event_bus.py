"""Central pub/sub event bus for inter-plugin communication."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class EventBus:
    """Central pub/sub event bus for inter-plugin communication."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[Dict] = []
        self._max_history = 1000

    async def emit(self, event: str, data: Any = None, source: str = "core"):
        """Emit an event to all subscribers."""
        envelope = {
            "event": event,
            "data": data,
            "source": source,
            "timestamp": time.time(),
        }
        self._history.append(envelope)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = list(self._subscribers.get(event, []))
        handlers += list(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                await handler(envelope)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    def subscribe(self, event: str, handler: Callable, source: str = "core"):
        """Subscribe to an event."""
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)
        logger.debug(f"{source} subscribed to {event}")

    def unsubscribe(self, event: str, handler: Callable):
        """Unsubscribe from an event."""
        if event in self._subscribers:
            self._subscribers[event] = [h for h in self._subscribers[event] if h != handler]

    def get_recent_events(self, event: str = None, limit: int = 50) -> List[Dict]:
        """Get recent events for debugging."""
        if event:
            return [e for e in self._history if e["event"] == event][-limit:]
        return self._history[-limit:]


event_bus = EventBus()