"""Core plugin infrastructure for DeskBuddy."""
from .event_bus import EventBus, event_bus
from .state_manager import StateManager, state_manager
from .plugin import DeskBuddyPlugin, PluginManifest, PluginContext, PluginStatus
from .plugin_loader import PluginLoader

__all__ = [
    "EventBus", "event_bus",
    "StateManager", "state_manager",
    "DeskBuddyPlugin", "PluginManifest", "PluginContext", "PluginStatus",
    "PluginLoader",
]