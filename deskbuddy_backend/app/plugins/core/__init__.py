"""Core plugin - wraps activity detection and sensor management."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.core.plugin import DeskBuddyPlugin, PluginManifest, PluginContext
from app.services.activity import activity_service
from app.services.device_settings import store

logger = logging.getLogger(__name__)

# Load manifest
_manifest_path = Path(__file__).parent / "manifest.json"
with open(_manifest_path) as f:
    manifest_data = json.load(f)

manifest = PluginManifest(**manifest_data)


class Plugin(DeskBuddyPlugin):
    def __init__(self, context: PluginContext):
        super().__init__(context)
        self.activity = activity_service

    async def on_load(self):
        self.ctx.logger.info("Core plugin loading")
        # Apply sleep thresholds from config
        thresholds = self.ctx.config.get("sleep_thresholds", {})
        if thresholds:
            self.activity.set_thresholds(thresholds)

    async def on_start(self):
        await self.activity.start()
        self.ctx.logger.info("Core plugin started")

    async def on_stop(self):
        await self.activity.stop()
        self.ctx.logger.info("Core plugin stopped")

    async def on_config_change(self, new_config):
        await super().on_config_change(new_config)
        thresholds = new_config.get("sleep_thresholds", {})
        if thresholds:
            self.activity.set_thresholds(thresholds)

    def get_state_keys(self):
        return ["activity", "expression", "sleep_stage", "app", "window", "idle_seconds"]

    def get_ws_channels(self):
        return ["deskbuddy_state", "activity"]