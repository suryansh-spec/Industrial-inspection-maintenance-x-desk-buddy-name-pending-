"""Base plugin class and manifest for DeskBuddy plugins."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class PluginStatus(str, Enum):
    DISABLED = "disabled"
    LOADING = "loading"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


class PluginManifest(BaseModel):
    """Plugin metadata and configuration schema."""
    id: str
    name: str
    version: str
    description: str
    author: str = "desk-buddy"
    category: str = "general"
    dependencies: List[str] = Field(default_factory=list)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    default_config: Dict[str, Any] = Field(default_factory=dict)
    enabled_by_default: bool = True


class PluginContext:
    """Injected into every plugin - provides access to core services."""

    def __init__(self, event_bus, state_manager, device_manager, config: Dict[str, Any]):
        self.event_bus = event_bus
        self.state = state_manager
        self.device = device_manager
        self.config = config
        self.logger = logging.getLogger(f"plugin.{config.get('id', 'unknown')}")

    async def emit(self, event: str, data: Any = None):
        await self.event_bus.emit(event, data, source=self.config.get("id"))

    async def subscribe(self, event: str, handler):
        self.event_bus.subscribe(event, handler, source=self.config.get("id"))

    async def send_to_device(self, cmd: str, payload: Dict[str, Any] = None):
        await self.device.send_command(cmd, payload or {})

    async def push_state(self, key: str, value: Any):
        await self.state.set(key, value, source=self.config.get("id"))


class DeskBuddyPlugin(ABC):
    """Base class for all plugins."""

    manifest: PluginManifest

    def __init__(self, context: PluginContext):
        self.ctx = context
        self.status = PluginStatus.DISABLED
        self._tasks: list = []

    @abstractmethod
    async def on_load(self) -> None:
        """Called when plugin is loaded. Initialize resources."""
        pass

    @abstractmethod
    async def on_start(self) -> None:
        """Called when plugin is started. Begin background work."""
        pass

    @abstractmethod
    async def on_stop(self) -> None:
        """Called when plugin is stopped. Clean up."""
        pass

    async def on_unload(self) -> None:
        """Called when plugin is unloaded. Final cleanup."""
        pass

    async def on_config_change(self, new_config: Dict[str, Any]) -> None:
        """Called when config is updated."""
        self.ctx.config = new_config

    def get_routes(self):
        """Return a FastAPI router for this plugin's endpoints."""
        return None

    def get_ws_channels(self) -> List[str]:
        """Return list of WebSocket channels this plugin publishes to."""
        return []

    def get_device_commands(self) -> List[str]:
        """Return list of device commands this plugin handles."""
        return []

    def get_state_keys(self) -> List[str]:
        """Return list of state keys this plugin manages."""
        return []

    async def _run_periodic(self, interval: float, coro):
        """Helper for periodic background tasks."""
        while True:
            try:
                await coro()
            except Exception as e:
                self.ctx.logger.error(f"Periodic task error: {e}")
            await asyncio.sleep(interval)

    def _add_task(self, coro):
        self._tasks.append(asyncio.create_task(coro))

    async def _cancel_tasks(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()