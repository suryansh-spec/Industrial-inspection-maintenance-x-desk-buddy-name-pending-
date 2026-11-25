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


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PluginLoader:
    """Discovers, loads, and manages plugins."""

    def __init__(self, event_bus: EventBus, state_manager: StateManager,
                 device_manager, config_dir: Optional[str] = None):
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.device_manager = device_manager
        self.config_dir = Path(config_dir) if config_dir else _PROJECT_ROOT
        self.plugins: Dict[str, DeskBuddyPlugin] = {}
        self.manifests: Dict[str, PluginManifest] = {}
        self._plugin_dir = _PROJECT_ROOT / "plugins"
        self._config_file = self.config_dir / "plugins.json"

    async def discover_plugins(self) -> List[str]:
        """Discover plugins from local directory and config."""
        discovered: List[str] = []
        disabled: set[str] = set()
        enabled_override: List[str] = []

        if self._config_file.exists():
            with open(self._config_file, encoding="utf-8") as f:
                config = json.load(f)
                disabled = set(config.get("disabled", []))
                enabled_override = list(config.get("enabled", []))

        def _scan_dir(base_dir: Path) -> None:
            if not base_dir.exists():
                return
            for p in base_dir.iterdir():
                manifest_path = p / "manifest.json"
                if not (p.is_dir() and manifest_path.exists()):
                    continue
                if p.name in disabled or p.name in discovered:
                    continue
                try:
                    with open(manifest_path, encoding="utf-8") as mf:
                        manifest_data = json.load(mf)
                    if not manifest_data.get("enabled_by_default", True) and p.name not in enabled_override:
                        continue
                except Exception:
                    pass
                discovered.append(p.name)

        # 1. Local plugin directory
        _scan_dir(self._plugin_dir)

        # 2. Built-in plugins (app/plugins/)
        _scan_dir(_PROJECT_ROOT / "app" / "plugins")

        # 3. Config file overrides
        for plugin_id in enabled_override:
            if plugin_id not in disabled and plugin_id not in discovered:
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