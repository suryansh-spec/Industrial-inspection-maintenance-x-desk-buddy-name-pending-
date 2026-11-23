"""Gaming plugin - wraps gaming service."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.core.plugin import DeskBuddyPlugin, PluginManifest, PluginContext

logger = logging.getLogger(__name__)

_manifest_path = Path(__file__).parent / "manifest.json"
with open(_manifest_path) as f:
    manifest_data = json.load(f)

manifest = PluginManifest(**manifest_data)


class Plugin(DeskBuddyPlugin):
    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.gaming_service = None

    async def on_load(self):
        from app.services.gaming import gaming_service
        self.gaming_service = gaming_service
        config = self.ctx.config
        self.gaming_service.configure(config)
        self.ctx.logger.info("Gaming plugin loading")

    async def on_start(self):
        await self.gaming_service.initialize()
        self._add_task(self._run_periodic(5.0, self.gaming_service.tick))
        self.ctx.logger.info("Gaming plugin started")

    async def on_stop(self):
        await self._cancel_tasks()
        await self.gaming_service.cleanup()
        self.ctx.logger.info("Gaming plugin stopped")

    async def on_config_change(self, new_config):
        await super().on_config_change(new_config)
        self.gaming_service.configure(new_config)

    def get_state_keys(self):
        return ["gaming"]

    def get_ws_channels(self):
        return ["gaming"]