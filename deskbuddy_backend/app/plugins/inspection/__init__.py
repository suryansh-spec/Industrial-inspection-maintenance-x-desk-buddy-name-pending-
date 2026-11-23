"""Inspection plugin - wraps vibration and vision inspection."""
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
        self.vibration_service = None
        self.vision_service = None

    async def on_load(self):
        try:
            from app.services.vibration import vibration_service
            self.vibration_service = vibration_service
        except ImportError:
            self.ctx.logger.warning("Vibration service not available")

        try:
            from app.services.vision import vision_service
            self.vision_service = vision_service
        except ImportError:
            self.ctx.logger.warning("Vision service not available")

        self.ctx.logger.info("Inspection plugin loading")

    async def on_start(self):
        if self.vibration_service:
            await self.vibration_service.initialize()
        if self.vision_service:
            await self.vision_service.initialize()
        self.ctx.logger.info("Inspection plugin started")

    async def on_stop(self):
        await self._cancel_tasks()
        if self.vibration_service:
            await self.vibration_service.cleanup()
        if self.vision_service:
            await self.vision_service.cleanup()
        self.ctx.logger.info("Inspection plugin stopped")

    def get_state_keys(self):
        return ["inspection"]

    def get_ws_channels(self):
        return ["inspection_result"]