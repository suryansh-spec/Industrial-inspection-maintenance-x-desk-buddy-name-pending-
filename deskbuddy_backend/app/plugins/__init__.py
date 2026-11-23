"""Built-in plugins for DeskBuddy."""
import json
from pathlib import Path

# Load plugins.json if it exists
_plugins_config = {}
_config_path = Path("plugins.json")
if _config_path.exists():
    with open(_config_path) as f:
        _plugins_config = json.load(f)

ENABLED_PLUGINS = _plugins_config.get("enabled", [
    "core",
    "music",
    "gaming",
    "inspection",
])