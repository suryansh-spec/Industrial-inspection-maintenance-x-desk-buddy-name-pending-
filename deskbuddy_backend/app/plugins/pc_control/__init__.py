"""PC Controller plugin - lock, volume, brightness, screenshot, open apps."""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import platform
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
        self._platform = platform.system().lower()

    async def on_load(self):
        self.ctx.logger.info("PC Controller plugin loading")

    async def on_start(self):
        self.ctx.logger.info("PC Controller plugin started")

    async def on_stop(self):
        await self._cancel_tasks()
        self.ctx.logger.info("PC Controller plugin stopped")

    async def lock_pc(self) -> bool:
        if self._platform == "windows":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
        elif self._platform == "darwin":
            subprocess.run(["pmset", "displaysleepnow"], check=True)
        else:
            subprocess.run(["loginctl", "lock-session"], check=True)
        return True

    async def set_volume(self, level: int) -> bool:
        level = max(0, min(100, level))
        if self._platform == "windows":
            subprocess.run([
                "powershell", "-Command",
                f"Set-Volume -Volume {level}"
            ], capture_output=True)
        elif self._platform == "darwin":
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
        return True

    async def set_brightness(self, level: int) -> bool:
        level = max(0, min(100, level))
        if self._platform == "windows":
            subprocess.run([
                "powershell", "-Command",
                f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
            ], capture_output=True)
        elif self._platform == "darwin":
            subprocess.run(["brightness", str(level/100)], check=True)
        else:
            subprocess.run(["brightnessctl", "set", f"{level}%"], check=True)
        return True

    async def take_screenshot(self, save_path: str = None) -> str:
        from PIL import ImageGrab
        import io, base64
        img = ImageGrab.grab()
        if save_path:
            img.save(save_path)
            return save_path
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    async def open_application(self, app_name: str) -> bool:
        if self._platform == "windows":
            subprocess.Popen(app_name, shell=True)
        elif self._platform == "darwin":
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen([app_name])
        return True

    def get_state_keys(self):
        return ["pc_control"]