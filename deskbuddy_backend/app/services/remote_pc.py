"""State pushed by a remote PC agent (see ``pc_agent/pc_agent.py``).

When the backend runs in the cloud it cannot see the user's PC, so a small
agent on the PC pushes the foreground app, idle time, system metrics and music
status to ``POST /api/v1/companion/pc-state``. While that data is fresh the
activity/companion services use it instead of sampling the local machine.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

# Seconds after which pushed data is considered stale (agent stopped).
REMOTE_TTL_SECONDS = 15.0


class RemotePCState:
    def __init__(self, ttl: float = REMOTE_TTL_SECONDS) -> None:
        self.ttl = ttl
        self._data: Dict[str, Any] = {}
        self._updated = 0.0

    def update(self, payload: Dict[str, Any]) -> None:
        self._data = dict(payload)
        self._updated = time.monotonic()

    def fresh(self) -> bool:
        return bool(self._data) and (time.monotonic() - self._updated) <= self.ttl

    def age_seconds(self) -> Optional[float]:
        if not self._updated:
            return None
        return time.monotonic() - self._updated

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "fresh": self.fresh(),
            "age_seconds": self.age_seconds(),
            "data": dict(self._data),
        }


remote_pc = RemotePCState()
