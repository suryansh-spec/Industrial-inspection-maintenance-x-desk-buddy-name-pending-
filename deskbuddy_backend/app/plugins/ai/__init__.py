"""AI Assistant plugin - Nemotron, STT, TTS (placeholder)."""
from __future__ import annotations

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

    async def on_load(self):
        self.ctx.logger.info("AI plugin loading (placeholder)")

    async def on_start(self):
        self.ctx.logger.info("AI plugin started (placeholder)")

    async def on_stop(self):
        await self._cancel_tasks()
        self.ctx.logger.info("AI plugin stopped")

    def get_state_keys(self):
        return ["ai"]