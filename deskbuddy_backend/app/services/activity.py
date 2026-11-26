"""
PC activity awareness for DeskBuddy.

Inspired by deskey-v2: the PC reports what the user is doing and how long they
have been idle, and the companion turns that into a small set of behaviours
(activity, sleep stage and facial expression).

The service is deliberately dependency-light. It uses the Windows API through
``ctypes`` (no pywin32 requirement) and falls back to safe defaults on other
platforms so the backend and its test-suite keep working everywhere.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import psutil

from app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# State vocabulary
# ============================================================================

class ActivityType(str, Enum):
    """What the user is doing on the PC."""

    CODING = "coding"
    BROWSING = "browsing"
    MUSIC = "music"
    GAMING = "gaming"
    WATCHING = "watching"
    MEETING = "meeting"
    TYPING = "typing"
    IDLE = "idle"
    UNKNOWN = "unknown"


class SleepStage(str, Enum):
    """Progressive inactivity, matching deskey-v2's behaviour."""

    ACTIVE = "active"
    SLEEPY = "sleepy"
    SLEEPING = "sleeping"
    DEEP_SLEEP = "deep_sleep"


class Expression(str, Enum):
    """Expressions understood by the OLED face firmware."""

    RELAXED = "relaxed"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SLEEPY = "sleepy"
    THINKING = "thinking"
    CURIOUS = "curious"
    EXCITED = "excited"
    SURPRISED = "surprised"
    CONFUSED = "confused"
    LAUGHING = "laughing"
    MUSIC = "music"
    TYPING = "typing"
    CODING = "coding"
    BROWSING = "browsing"
    GAMING = "gaming"
    WATCHING = "watching"
    SLEEPING = "sleeping"
    DEEP_SLEEP = "deep_sleep"
    AUTONOMOUS = "autonomous"


# ============================================================================
# Classification rules
# ============================================================================

_CODING_APPS = {
    "code",
    "code - insiders",
    "cursor",
    "pycharm",
    "pycharm64",
    "idea",
    "idea64",
    "webstorm",
    "clion",
    "goland",
    "rider",
    "android studio",
    "studio64",
    "sublime_text",
    "sublime text",
    "notepad++",
    "vim",
    "nvim",
    "neovim",
    "emacs",
    "arduino ide",
    "arduino-ide",
    "platformio",
    "jupyter",
    "jupyter-notebook",
    "windowsterminal",
    "wt",
    "powershell",
    "pwsh",
    "cmd",
    "conhost",
    "bash",
    "wsl",
    "git bash",
    "cmder",
    "alacritty",
    "wezterm",
    "postman",
}

_BROWSER_APPS = {
    "chrome",
    "google chrome",
    "msedge",
    "microsoft edge",
    "firefox",
    "brave",
    "brave browser",
    "opera",
    "opera gx",
    "vivaldi",
    "arc",
    "safari",
    "librewolf",
    "waterfox",
}

_MUSIC_APPS = {
    "spotify",
    "ytmusic",
    "youtube music",
    "youtube music desktop app",
    "tidal",
    "applemusic",
    "apple music",
    "musicbee",
    "foobar2000",
    "deezer",
    "soundcloud",
    "wmplayer",
    "music",
}

_VIDEO_APPS = {
    "vlc",
    "mpv",
    "mpc-hc",
    "mpc-hc64",
    "potplayermini64",
    "plex",
    "plexmediaplayer",
    "netflix",
    "primevideo",
}

_GAMING_APPS = {
    "steam",
    "steamwebhelper",
    "epicgameslauncher",
    "riotclient",
    "riotclientservices",
    "battle.net",
    "battlenet",
    "gog galaxy",
    "galaxyclient",
    "ubisoft connect",
    "upc",
    "ea app",
    "eadesktop",
    "origin",
    "xboxapp",
    "minecraft",
    "javaw",
    "leagueclient",
    "league of legends",
    "valorant",
    "cs2",
    "dota2",
    "rocketleague",
    "eldenring",
    "gta5",
    "gtav",
    "cyberpunk2077",
    "witcher3",
    "bg3",
    "destiny2",
    "r5apex",
    "overwatch",
    "fortnite",
    "tekken",
}

_MEETING_APPS = {
    "zoom",
    "zoom.us",
    "teams",
    "ms-teams",
    "msteams",
    "webex",
    "webexmta",
    "skype",
    "discord",
    "slack",
}

_TERMINAL_APPS = {
    "windowsterminal",
    "wt",
    "powershell",
    "pwsh",
    "cmd",
    "conhost",
    "bash",
    "wsl",
    "git bash",
    "cmder",
    "alacritty",
    "wezterm",
}

_CHAT_APPS = {
    "discord",
    "slack",
    "telegram",
    "whatsapp",
    "signal",
    "teams",
    "ms-teams",
    "zoom",
}

# Title hints are checked case-insensitively and are intentionally specific
# enough that a foreground app still wins over background audio.
_CODING_TITLE_HINTS = (
    "visual studio code",
    "cursor -",
    "pycharm",
    "intellij",
    "webstorm",
    "android studio",
    "sublime text",
    "neovim",
    "vim -",
    "arduino ide",
    "platformio",
    "jupyter",
    "google colab",
    "github codespaces",
)

_WATCHING_TITLE_HINTS = (
    "netflix",
    "twitch",
    "prime video",
    "disney+",
    "hulu",
    "hbo max",
    "plex",
    "crunchyroll",
    "hotstar",
    "vlc media player",
    "mpv",
    "youtube - ",
    "youtube.com",
)

_MUSIC_TITLE_HINTS = (
    "youtube music",
    "yt music",
    "spotify",
    "soundcloud",
    "tidal",
    "apple music",
    "deezer",
    "musicbee",
    "foobar2000",
)

_MEDIA_PROCESS_NAMES = {
    "spotify",
    "ytmusic",
    "youtube music",
    "youtube music desktop app",
    "tidal",
    "applemusic",
    "apple music",
    "musicbee",
    "foobar2000",
    "deezer",
    "wmplayer",
    "vlc",
    "mpv",
}

_DESKTOP_APPS = {
    "",
    "explorer",
    "desktop",
    "program manager",
    "applicationframehost",
    "searchhost",
    "startmenuexperiencehost",
    "shellexperiencehost",
}


def _normalise(value: str) -> str:
    return (value or "").strip().lower().removeprefix("\\").removesuffix(".exe").strip()


def classify_activity(
    app_name: str,
    window_title: str,
    audio_active: bool = False,
) -> ActivityType:
    """Turn a foreground window and audio flag into a coarse activity.

    Foreground context deliberately has priority over background audio. This is
    the deskey-v2 rule: Spotify playing while VS Code is focused is *coding*,
    not *music*.
    """

    app = _normalise(app_name)
    title = (window_title or "").lower()

    if app in _MEETING_APPS:
        return ActivityType.MEETING

    if app in _CODING_APPS or app in _TERMINAL_APPS:
        return ActivityType.CODING

    if any(hint in title for hint in _CODING_TITLE_HINTS):
        return ActivityType.CODING

    if app in _GAMING_APPS:
        return ActivityType.GAMING

    # Unreal Engine games (Tekken, many others) expose a process named
    # ``<Game>-Win64-Shipping.exe``. This catches them without shipping a
    # per-game database.
    if app.endswith("-win64-shipping") or app.endswith("-win32-shipping"):
        return ActivityType.GAMING

    if app in _MUSIC_APPS or any(hint in title for hint in _MUSIC_TITLE_HINTS):
        return ActivityType.MUSIC

    if app in _VIDEO_APPS or any(hint in title for hint in _WATCHING_TITLE_HINTS):
        return ActivityType.WATCHING

    if app in _BROWSER_APPS:
        return ActivityType.BROWSING

    if audio_active and app in _DESKTOP_APPS:
        return ActivityType.MUSIC

    if app in _CHAT_APPS:
        return ActivityType.TYPING

    return ActivityType.UNKNOWN


def sleep_stage_for(
    idle_seconds: float,
    sleepy_seconds: float = 30,
    sleep_seconds: float = 120,
    deep_sleep_seconds: float = 300,
) -> SleepStage:
    """Map PC idle time to a progressive sleep stage."""

    idle = max(0.0, float(idle_seconds))
    if idle >= max(deep_sleep_seconds, sleep_seconds, sleepy_seconds):
        return SleepStage.DEEP_SLEEP
    if idle >= max(sleep_seconds, sleepy_seconds):
        return SleepStage.SLEEPING
    if idle >= sleepy_seconds:
        return SleepStage.SLEEPY
    return SleepStage.ACTIVE


_ACTIVITY_EXPRESSION = {
    ActivityType.CODING: Expression.CODING,
    ActivityType.BROWSING: Expression.BROWSING,
    ActivityType.MUSIC: Expression.MUSIC,
    ActivityType.GAMING: Expression.GAMING,
    ActivityType.WATCHING: Expression.WATCHING,
    ActivityType.MEETING: Expression.THINKING,
    ActivityType.TYPING: Expression.TYPING,
    ActivityType.IDLE: Expression.RELAXED,
    ActivityType.UNKNOWN: Expression.RELAXED,
}


def expression_for(activity: ActivityType, sleep_stage: SleepStage) -> Expression:
    """Choose the face expression for an activity and sleep stage."""

    if sleep_stage == SleepStage.DEEP_SLEEP:
        return Expression.DEEP_SLEEP
    if sleep_stage == SleepStage.SLEEPING:
        return Expression.SLEEPING
    if sleep_stage == SleepStage.SLEEPY:
        return Expression.SLEEPY
    return _ACTIVITY_EXPRESSION.get(activity, Expression.RELAXED)


_ACTIVITY_DESCRIPTION = {
    ActivityType.CODING: "Coding",
    ActivityType.BROWSING: "Browsing",
    ActivityType.MUSIC: "Listening to music",
    ActivityType.GAMING: "Gaming",
    ActivityType.WATCHING: "Watching",
    ActivityType.MEETING: "In a meeting",
    ActivityType.TYPING: "Chatting",
    ActivityType.IDLE: "Idle",
    ActivityType.UNKNOWN: "At the desk",
}


# ============================================================================
# Windows API helpers
# ============================================================================

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_ulong),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _windows_user32():
    if platform.system() != "Windows":
        return None
    try:
        return ctypes.windll.user32
    except Exception:  # pragma: no cover - non-Windows / restricted session
        return None


def get_idle_seconds() -> float:
    """Return seconds since the last keyboard/mouse input on Windows."""

    user32 = _windows_user32()
    if user32 is None:
        return 0.0

    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0

        # GetTickCount and LASTINPUTINFO.dwTime are both 32-bit milliseconds.
        tick_count = user32.GetTickCount() & 0xFFFFFFFF
        elapsed = (tick_count - info.dwTime) & 0xFFFFFFFF
        return max(0.0, elapsed / 1000.0)
    except Exception:  # pragma: no cover - API unavailable
        return 0.0


def get_foreground_window() -> Tuple[str, str, int]:
    """Return ``(process_name, window_title, pid)`` for the foreground window."""

    user32 = _windows_user32()
    if user32 is None:
        return "", "", 0

    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", "", 0

        length = int(user32.GetWindowTextLengthW(hwnd))
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_value = int(pid.value)

        app_name = ""
        if pid_value:
            try:
                app_name = psutil.Process(pid_value).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                app_name = ""

        return app_name, title_buffer.value, pid_value
    except Exception:  # pragma: no cover - API unavailable
        return "", "", 0


# ============================================================================
# Activity service
# ============================================================================

@dataclass
class ActivitySnapshot:
    activity: ActivityType
    expression: Expression
    sleep_stage: SleepStage
    app_name: str
    window_title: str
    pid: int
    idle_seconds: float
    audio_active: bool
    sampled_at: datetime
    activity_since: datetime


class ActivityService:
    """Continuously samples PC context and exposes a small state snapshot."""

    def __init__(
        self,
        sleepy_seconds: Optional[float] = None,
        sleep_seconds: Optional[float] = None,
        deep_sleep_seconds: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ):
        self._sleepy_seconds = float(
            sleepy_seconds
            if sleepy_seconds is not None
            else getattr(settings, "companion_sleepy_seconds", 30)
        )
        self._sleep_seconds = float(
            sleep_seconds
            if sleep_seconds is not None
            else getattr(settings, "companion_sleep_seconds", 120)
        )
        self._deep_sleep_seconds = float(
            deep_sleep_seconds
            if deep_sleep_seconds is not None
            else getattr(settings, "companion_deep_sleep_seconds", 300)
        )
        self._poll_interval = max(
            0.5,
            float(
                poll_interval
                if poll_interval is not None
                else getattr(settings, "companion_poll_interval", 1.0)
            ),
        )

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._snapshot: Optional[ActivitySnapshot] = None
        self._heartbeat = time.monotonic()

        self._manual_expression: Optional[Expression] = None
        self._manual_until = 0.0

        self._audio_cached_at = 0.0
        self._audio_cached = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    @property
    def thresholds(self) -> Dict[str, float]:
        return {
            "sleepy_seconds": self._sleepy_seconds,
            "sleep_seconds": self._sleep_seconds,
            "deep_sleep_seconds": self._deep_sleep_seconds,
            "poll_interval": self._poll_interval,
        }

    def set_thresholds(self, values: Dict[str, Any]) -> Dict[str, float]:
        """Update inactivity thresholds (used by the web panel)."""
        for key, attr in (
            ("sleepy_seconds", "_sleepy_seconds"),
            ("sleep_seconds", "_sleep_seconds"),
            ("deep_sleep_seconds", "_deep_sleep_seconds"),
        ):
            if key in values:
                try:
                    setattr(self, attr, max(1, int(values[key])))
                except (TypeError, ValueError):
                    continue
        return self.thresholds

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._sample()
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Activity service started (sleepy=%.0fs sleep=%.0fs deep=%.0fs)",
            self._sleepy_seconds,
            self._sleep_seconds,
            self._deep_sleep_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Activity service stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                self._sample()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Activity sample failed")
            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def _sample(self, force: bool = False) -> ActivitySnapshot:
        now = datetime.now(timezone.utc)
        from app.services.remote_pc import remote_pc

        if remote_pc.fresh():
            # A PC agent is pushing its state (cloud deployment).
            app_name = str(remote_pc.get("app", "") or "")
            window_title = str(remote_pc.get("window", "") or "")
            pid = int(remote_pc.get("pid", 0) or 0)
            idle_seconds = float(remote_pc.get("idle_seconds", 0.0) or 0.0)
            audio_active = bool(remote_pc.get("audio_active", False))
        else:
            app_name, window_title, pid = get_foreground_window()
            idle_seconds = get_idle_seconds()
            audio_active = self._detect_audio_active()

        activity = classify_activity(app_name, window_title, audio_active)
        if idle_seconds >= self._deep_sleep_seconds:
            activity = ActivityType.IDLE

        sleep_stage = sleep_stage_for(
            idle_seconds,
            sleepy_seconds=self._sleepy_seconds,
            sleep_seconds=self._sleep_seconds,
            deep_sleep_seconds=self._deep_sleep_seconds,
        )

        previous = self._snapshot
        activity_since = now
        if previous and previous.activity == activity:
            activity_since = previous.activity_since

        expression = expression_for(activity, sleep_stage)
        expression = self._apply_manual_expression(expression)

        snapshot = ActivitySnapshot(
            activity=activity,
            expression=expression,
            sleep_stage=sleep_stage,
            app_name=app_name,
            window_title=window_title,
            pid=pid,
            idle_seconds=idle_seconds,
            audio_active=audio_active,
            sampled_at=now,
            activity_since=activity_since,
        )
        self._snapshot = snapshot
        return snapshot

    def _apply_manual_expression(self, expression: Expression) -> Expression:
        if self._manual_expression is None:
            return expression
        if time.monotonic() >= self._manual_until:
            self._manual_expression = None
            self._manual_until = 0.0
            return expression
        return self._manual_expression

    def _detect_audio_active(self) -> bool:
        """Best-effort audio detection without requiring pycaw.

        The music controller is the most reliable source when it has a live
        playback status. Otherwise known media processes are used as a cheap
        heuristic. Foreground activity still wins in classification.
        """

        now = time.monotonic()
        if now - self._audio_cached_at < 5.0:
            return self._audio_cached

        active = False
        try:
            from app.services.music import music_controller

            status = music_controller.get_status()
            active = bool(getattr(status, "playing", False))
        except Exception:
            active = False

        if not active:
            try:
                for process in psutil.process_iter(["name"]):
                    name = _normalise(process.info.get("name", ""))
                    if name in _MEDIA_PROCESS_NAMES:
                        active = True
                        break
            except Exception:
                active = False

        self._audio_cached = active
        self._audio_cached_at = now
        return active

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------
    def touch_heartbeat(self) -> None:
        """Mark the PC bridge as alive (used by /companion/heartbeat)."""

        self._heartbeat = time.monotonic()

    def heartbeat_age_ms(self) -> int:
        return int((time.monotonic() - self._heartbeat) * 1000)

    def set_manual_expression(
        self,
        expression: str | Expression,
        duration_seconds: float = 30.0,
    ) -> Expression:
        try:
            parsed = expression if isinstance(expression, Expression) else Expression(expression)
        except ValueError as exc:
            valid = ", ".join(item.value for item in Expression)
            raise ValueError(f"Unknown expression '{expression}'. Valid: {valid}") from exc

        self._manual_expression = parsed
        self._manual_until = (
            time.monotonic() + max(1.0, float(duration_seconds))
            if duration_seconds > 0
            else float("inf")
        )
        # Force a re-sample so the manual expression takes effect immediately
        self._sample(force=True)
        logger.info("Manual expression set to %s for %.0fs", parsed.value, duration_seconds)
        return parsed

    def clear_manual_expression(self) -> None:
        self._manual_expression = None
        self._manual_until = 0.0

    def get_context(self, force: bool = False) -> Dict[str, Any]:
        """Return the current PC context as a JSON-friendly dictionary."""

        snapshot = self._snapshot
        # Force re-sample if manual expression is active or just expired
        manual_active = self._manual_expression is not None and (
            self._manual_until == float("inf") or time.monotonic() < self._manual_until
        )
        manual_expired = self._manual_expression is not None and time.monotonic() >= self._manual_until and self._manual_until != float("inf")
        if force or snapshot is None or manual_active or manual_expired:
            snapshot = self._sample(force=True)

        return {
            "activity": snapshot.activity.value,
            "expression": snapshot.expression.value,
            "sleep_stage": snapshot.sleep_stage.value,
            "app": snapshot.app_name,
            "window": snapshot.window_title,
            "pid": snapshot.pid,
            "idle_seconds": round(snapshot.idle_seconds, 1),
            "audio_active": snapshot.audio_active,
            "description": _ACTIVITY_DESCRIPTION.get(snapshot.activity, "At the desk"),
            "activity_since": snapshot.activity_since.isoformat(),
            "sampled_at": snapshot.sampled_at.isoformat(),
            "heartbeat_age_ms": self.heartbeat_age_ms(),
            "thresholds": self.thresholds,
            "manual_expression": (
                self._manual_expression.value if self._manual_expression else None
            ),
        }

    def get_snapshot(self) -> ActivitySnapshot:
        if self._snapshot is None:
            return self._sample(force=True)
        return self._snapshot


# Shared instance used by the API and the background push task.
activity_service = ActivityService()
