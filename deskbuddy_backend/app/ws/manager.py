"""
WebSocket connection manager with channel subscriptions.
"""
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks active WebSocket connections and their channel subscriptions."""

    def __init__(self):
        self.active_connections: Dict[WebSocket, Set[str]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new connection and start tracking it."""
        await websocket.accept()
        self.active_connections[websocket] = set()
        logger.info("WebSocket connected (%d active)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection from the tracker."""
        self.active_connections.pop(websocket, None)
        logger.info("WebSocket disconnected (%d active)", len(self.active_connections))

    def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Subscribe a connection to a channel."""
        if websocket in self.active_connections:
            self.active_connections[websocket].add(channel)

    def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Remove a channel subscription."""
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(channel)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send a message to a single connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

    async def broadcast(self, channel: str, message: dict) -> None:
        """Broadcast a message to every connection subscribed to a channel."""
        payload = {"channel": channel, "data": message}
        dead = []
        for connection, channels in list(self.active_connections.items()):
            # Connections without explicit subscriptions receive everything.
            if channels and channel not in channels:
                continue
            try:
                await connection.send_json(payload)
            except Exception:
                dead.append(connection)

        for connection in dead:
            self.disconnect(connection)

    def get_connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self.active_connections)


# Global manager used by the app and background tasks.
ws_manager = ConnectionManager()
