"""Music plugin - wraps music controller, cover art, lyrics, and spectrum."""
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
        self.music_controller = None
        self.cover_art_service = None
        self._cover_art_key = None
        self._lyrics_track = None

    async def on_load(self):
        from app.services.music import MusicController
        from app.services.cover_art import CoverArtService
        self.music_controller = MusicController()
        self.cover_art_service = CoverArtService()
        self.ctx.logger.info("Music plugin loading")

    async def on_start(self):
        await self.music_controller.initialize()
        self.ctx.logger.info("Music plugin started")

    async def on_stop(self):
        await self._cancel_tasks()
        await self.music_controller.close()
        await self.cover_art_service.close()
        self.ctx.logger.info("Music plugin stopped")

    async def on_config_change(self, new_config):
        await super().on_config_change(new_config)
        if "provider" in new_config:
            await self.music_controller.switch_provider(new_config["provider"])

    def get_state_keys(self):
        return ["music", "lyrics", "spectrum"]

    def get_ws_channels(self):
        return ["music", "spectrum", "lyrics"]

    async def _sync_cover_art(self, title: str, artist: str, album_art_url: str = None):
        """Fetch and send cover art to device."""
        if not title:
            return
        key = f"{title.strip().lower()}|{artist.strip().lower()}"
        if key == self._cover_art_key:
            return
        self._cover_art_key = key

        try:
            assets = await self.cover_art_service.get_cover_assets(title, artist, album_art_url)
            if not assets:
                return

            manager = self.ctx.device.get_serial_manager() if hasattr(self.ctx.device, 'get_serial_manager') else None
            if not manager:
                from app.services import serial_manager as sm
                manager = sm.get_serial_manager()
            if manager and manager.is_connected:
                await manager.send_command("cover_thumb", {
                    "track": title[:32],
                    "data": assets["thumb_b64"],
                    "dominant_color": assets.get("dominant_color"),
                })
                await manager.send_command("cover_bg", {
                    "track": title[:32],
                    "w": 32, "h": 40,
                    "data": assets["bg_b64"],
                })
        except Exception as e:
            self.ctx.logger.debug("Failed to dispatch cover art: %s", e)

    def clear_cover_art_cache(self):
        self._cover_art_key = None