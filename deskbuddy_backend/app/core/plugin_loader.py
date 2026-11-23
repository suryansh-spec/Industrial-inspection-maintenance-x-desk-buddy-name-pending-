"""Plugin discovery, loading, and lifecycle management."""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .plugin import DeskBuddyPlugin, PluginManifest, PluginContext, PluginStatus
from .event_bus import EventBus
from .state_manager import StateManager

logger = logging.getLogger(__name__)


class PluginLoader:
    """Discovers, loads, and manages plugins."""

    def __init__(self, event_bus: EventBus, state_manager: StateManager,
                 device_manager, config_dir: str = "plugins"):
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.device_manager = device_manager
        self.config_dir = Path(config_dir)
        self.plugins: Dict[str, DeskBuddyPlugin] = {}
        self.manifests: Dict[str, PluginManifest] = {}
        self._plugin_dir = Path("plugins")
        self._config_file = self.config_dir / "plugins.json"

    async def discover_plugins(self) -> List[str]:
        """Discover plugins from local directory and config."""
        discovered = []

        # 1. Local plugin directory
        if self._plugin_dir.exists():
            for p in self._plugin_dir.iterdir():
                if p.is_dir() and (p / "manifest.json").exists():
                    discovered.append(p.name)

        # 2. Built-in plugins (app/plugins/)
        builtin_dir = Path("app/plugins")
        if builtin_dir.exists():
            for p in builtin_dir.iterdir():
                if p.is_dir() and (p / "manifest.json").exists():
                    discovered.append(p.name)

        # 3. Config file overrides
        if self._config_file.exists():
            with open(self._config_file) as f:
                config = json.load(f)
                for plugin_id in config.get("enabled", []):
                    if plugin_id not in discovered:
                        discovered.append(plugin_id)

        return discovered

    async def load_plugin(self, plugin_id: str, config: Dict[str, Any] = None) -> bool:
        """Load a plugin by ID."""
        if plugin_id in self.plugins:
            logger.warning(f"Plugin {plugin_id} already loaded")
            return True

        try:
            module = self._import_plugin(plugin_id)
            if not module:
                return False

            manifest = getattr(module, "manifest", None)
            if not manifest:
                logger.error(f"Plugin {plugin_id} has no manifest")
                return False

            # Validate dependencies
            for dep in manifest.dependencies:
                if dep not in self.plugins:
                    logger.error(f"Plugin {plugin_id} missing dependency: {dep}")
                    return False

            config = config or manifest.default_config
            context = PluginContext(
                event_bus=self.event_bus,
                state_manager=self.state_manager,
                device_manager=self.device_manager,
                config={"id": plugin_id, **config},
            )

            plugin_class = module.Plugin
            plugin = plugin_class(context)
            plugin.manifest = manifest

            await plugin.on_load()
            plugin.status = PluginStatus.LOADING

            self.plugins[plugin_id] = plugin
            self.manifests[plugin_id] = manifest

            logger.info(f"Loaded plugin: {plugin_id} v{manifest.version}")
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_id}: {e}")
            return False

    async def start_plugin(self, plugin_id: str) -> bool:
        """Start a loaded plugin."""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        try:
            await plugin.on_start()
            plugin.status = PluginStatus.RUNNING
            logger.info(f"Started plugin: {plugin_id}")
            return True
        except Exception as e:
            plugin.status = PluginStatus.ERROR
            logger.error(f"Failed to start plugin {plugin_id}: {e}")
            return False

    async def stop_plugin(self, plugin_id: str) -> bool:
        """Stop a running plugin."""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        try:
            await plugin._cancel_tasks()
            await plugin.on_stop()
            plugin.status = PluginStatus.STOPPED
            logger.info(f"Stopped plugin: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop plugin {plugin_id}: {e}")
            return False

    async def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin completely."""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        await self.stop_plugin(plugin_id)
        await plugin.on_unload()
        del self.plugins[plugin_id]
        del self.manifests[plugin_id]
        logger.info(f"Unloaded plugin: {plugin_id}")
        return True

    def _import_plugin(self, plugin_id: str):
        """Import a plugin module."""
        # Try built-in plugins (app/plugins/)
        builtin_path = Path("app/plugins") / plugin_id / "__init__.py"
        if builtin_path.exists():
            spec = importlib.util.spec_from_file_location(
                f"app.plugins.{plugin_id}", builtin_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        # Try external plugins (plugins/)
        external_path = self._plugin_dir / plugin_id / "__init__.py"
        if external_path.exists():
            spec = importlib.util.spec_from_file_location(plugin_id, external_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        return None

    def get_plugin(self, plugin_id: str):
        return self.plugins.get(plugin_id)

    def list_plugins(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": pid,
                "name": p.manifest.name,
                "version": p.manifest.version,
                "status": p.status.value,
                "category": p.manifest.category,
                "config": p.ctx.config,
            }
            for pid, p in self.plugins.items()
        ]

    async def start_all(self):
        """Load and start all discovered plugins."""
        plugins = await self.discover_plugins()
        for pid in plugins:
            if await self.load_plugin(pid):
                await self.start_plugin(pid)

    async def stop_all(self):
        """Stop and unload all plugins."""
        for pid in list(self.plugins.keys()):
            await self.unload_plugin(pid)

    def get_all_routes(self):
        """Collect routes from all plugins."""
        routes = []
        for plugin in self.plugins.values():
            router = plugin.get_routes()
            if router:
                routes.append(router)
        return routes

    def get_all_state_keys(self) -> List[str]:
        """Collect state keys from all plugins."""
        keys = []
        for plugin in self.plugins.values():
            keys.extend(plugin.get_state_keys())
        return keys