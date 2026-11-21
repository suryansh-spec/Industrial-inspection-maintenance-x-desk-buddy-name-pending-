"""
WebSocket Connection Manager - Handles WebSocket connections and message broadcasting.
"""
import asyncio
import json
import logging
from typing import Dict, List, Set, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and pub/sub messaging."""
    
    def __init__(self):
        # Active connections: {websocket: {subscriptions: set, metadata: dict}}
        self._connections: Dict[WebSocket, dict] = {}
        # Channel subscribers: {channel: set(websockets)}
        self._channels: Dict[str, Set[WebSocket]] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None):
        """Accept new WebSocket connection."""
        await websocket.accept()
        
        async with self._lock:
            self._connections[websocket] = {
                "client_id": client_id or id(websocket),
                "subscriptions": set(),
                "connected_at": asyncio.get_event_loop().time()
            }
        
        # Subscribe to default channels
        await self.subscribe(websocket, "all")
        await self.subscribe(websocket, "notifications")
        
        logger.info(f"Client connected: {self._connections[websocket]['client_id']}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        async def _disconnect():
            async with self._lock:
                if websocket in self._connections:
                    # Remove from all channels
                    for channel in self._connections[websocket]["subscriptions"]:
                        if channel in self._channels:
                            self._channels[channel].discard(websocket)
                    
                    del self._connections[websocket]
                    logger.info(f"Client disconnected")
        
        # Run sync since we might be called from non-async context
        try:
            asyncio.run(_disconnect())
        except RuntimeError:
            # Already in event loop
            asyncio.create_task(_disconnect())
    
    async def subscribe(self, websocket: WebSocket, channel: str):
        """Subscribe websocket to a channel."""
        async with self._lock:
            if websocket not in self._connections:
                return
            
            if channel not in self._channels:
                self._channels[channel] = set()
            
            self._channels[channel].add(websocket)
            self._connections[websocket]["subscriptions"].add(channel)
            logger.debug(f"Client subscribed to {channel}")
    
    async def unsubscribe(self, websocket: WebSocket, channel: str):
        """Unsubscribe websocket from a channel."""
        async with self._lock:
            if channel in self._channels:
                self._channels[channel].discard(websocket)
                if websocket in self._connections:
                    self._connections[websocket]["subscriptions"].discard(channel)
    
    async def send_personal_message(self, websocket: WebSocket, message: dict):
        """Send message to specific websocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, channel: str, message: dict, exclude: Optional[WebSocket] = None):
        """Broadcast message to all subscribers of a channel."""
        if channel not in self._channels:
            return
        
        message_str = json.dumps(message)
        disconnected = []
        
        for websocket in self._channels[channel]:
            if websocket == exclude:
                continue
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.warning(f"Broadcast failed for client: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws)
    
    async def broadcast_json(self, channel: str, data: dict, exclude: Optional[WebSocket] = None):
        """Broadcast JSON data to channel."""
        await self.broadcast(channel, data, exclude)
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)
    
    def get_channel_subscribers(self, channel: str) -> int:
        """Get number of subscribers to a channel."""
        return len(self._channels.get(channel, set()))
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self._connections),
            "channels": {ch: len(subs) for ch, subs in self._channels.items()},
            "clients": [
                {
                    "client_id": info["client_id"],
                    "subscriptions": list(info["subscriptions"]),
                    "connected_at": info["connected_at"]
                }
                for info in self._connections.values()
            ]
        }