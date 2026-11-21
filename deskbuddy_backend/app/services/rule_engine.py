"""Notification rules engine.

Rules are user-authored IF/THEN documents from the web panel:

    {"id": "...", "name": "High CPU", "metric": "cpu", "op": ">",
     "threshold": 80, "title": "High CPU", "message": "CPU at {value}%",
     "priority": "high", "cooldown": 300, "enabled": true}

Evaluated on a short tick; a rule fires at most once per cooldown window.
"""
from __future__ import annotations

import logging
import operator
import time
import uuid
from typing import Any, Dict, List, Optional

from app.services.device_settings import METRICS, store

logger = logging.getLogger(__name__)

_OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

_PRIORITY_INT = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
_METRIC_LABEL = {m["id"]: m["label"] for m in METRICS}


def new_rule(values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rule = {
        "id": uuid.uuid4().hex[:12],
        "name": "New rule",
        "metric": "cpu",
        "op": ">",
        "threshold": 80,
        "title": "DeskBuddy alert",
        "message": "{metric} is {value}",
        "priority": "normal",
        "cooldown": 300,
        "enabled": True,
    }
    if values:
        rule.update({k: v for k, v in values.items() if v is not None})
    rule["id"] = rule.get("id") or uuid.uuid4().hex[:12]
    return rule


def normalize_rule(raw: Dict[str, Any]) -> Dict[str, Any]:
    rule = new_rule()
    rule.update({k: v for k, v in (raw or {}).items() if v is not None})
    rule["id"] = str(rule.get("id") or uuid.uuid4().hex[:12])
    if rule.get("metric") not in _METRIC_LABEL:
        rule["metric"] = "cpu"
    if rule.get("op") not in _OPS:
        rule["op"] = ">"
    try:
        rule["threshold"] = float(rule.get("threshold", 80))
    except (TypeError, ValueError):
        rule["threshold"] = 80.0
    if rule.get("priority") not in _PRIORITY_INT:
        rule["priority"] = "normal"
    try:
        rule["cooldown"] = max(10, int(rule.get("cooldown", 300)))
    except (TypeError, ValueError):
        rule["cooldown"] = 300
    rule["enabled"] = bool(rule.get("enabled", True))
    rule["name"] = str(rule.get("name") or rule["metric"])
    rule["title"] = str(rule.get("title") or rule["name"])
    rule["message"] = str(rule.get("message") or "{metric} is {value}")
    return rule


def metric_values() -> Dict[str, float]:
    try:
        from app.services.companion import companion_service
        summary = companion_service.get_summary()
    except Exception:  # pragma: no cover - degraded mode
        return {}
    values: Dict[str, float] = {}
    for metric in METRICS:
        container = summary.get(metric.get("source", "metrics")) or {}
        raw = container.get(metric["field"])
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            values[metric["id"]] = float(raw)
    return values


class RuleEngine:
    def __init__(self) -> None:
        self._last_fire: Dict[str, float] = {}

    def evaluate(self, values: Dict[str, float], now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Return the rules that should fire right now (pure, testable)."""
        now = time.time() if now is None else now
        fired: List[Dict[str, Any]] = []
        for raw in store.rules():
            rule = normalize_rule(raw)
            if not rule.get("enabled"):
                continue
            value = values.get(rule["metric"])
            if value is None:
                continue
            try:
                exceeded = _OPS[rule["op"]](value, rule["threshold"])
            except Exception:  # pragma: no cover - defensive
                continue
            if not exceeded:
                continue
            last = self._last_fire.get(rule["id"], 0.0)
            if now - last < rule["cooldown"]:
                continue
            self._last_fire[rule["id"]] = now
            fired.append({"rule": rule, "value": value})
        return fired

    async def fire(self, rule: Dict[str, Any], value: float) -> None:
        label = _METRIC_LABEL.get(rule["metric"], rule["metric"])
        fmt = {
            "value": f"{value:.1f}".rstrip("0").rstrip("."),
            "metric": label,
            "threshold": rule["threshold"],
            "name": rule["name"],
        }
        try:
            message = rule["message"].format(**fmt)
        except Exception:
            message = f"{label} is {fmt['value']}"
        title = rule["title"]
        priority = rule["priority"]

        logger.info("Rule fired: %s (%s)", title, message)

        # Live web toast + persistent history.
        try:
            from app.services.notification_service import notification_service
            await notification_service.send_notification(
                title=title,
                message=message,
                priority=priority,
                category="rule",
                metadata={"rule_id": rule["id"], "metric": rule["metric"], "value": value},
            )
        except Exception:
            logger.debug("Could not persist rule notification", exc_info=True)

        # Immediate device banner + websocket state.
        try:
            from app.services.companion import companion_service
            await companion_service.push_notification(
                title=title,
                message=message,
                priority=_PRIORITY_INT.get(priority, 1),
            )
        except Exception:
            logger.debug("Could not push rule notification to device", exc_info=True)

    async def tick(self) -> None:
        values = metric_values()
        if not values:
            return
        for item in self.evaluate(values):
            try:
                await self.fire(item["rule"], item["value"])
            except Exception:  # pragma: no cover - one bad rule must not stop the loop
                logger.debug("Rule dispatch failed", exc_info=True)


rule_engine = RuleEngine()
