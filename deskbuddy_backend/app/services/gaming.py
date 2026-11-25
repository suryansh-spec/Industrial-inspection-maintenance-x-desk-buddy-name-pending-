"""
Gaming Mode Service.

Detects game launches/exits, tracks sessions, monitors GPU/CPU/VRAM/temps,
and triggers temperature alerts.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import psutil

logger = logging.getLogger(__name__)

# Known game process names (lowercase, without .exe)
KNOWN_GAMES = {
    "eldenring", "cyberpunk2077", "witcher3", "godofwar", "rdr2",
    "gta5", "gtav", "skyrim", "fallout4", "fallout76", "doom",
    "doometernal", "halo", "haloinfinite", "forza", "fh5", "fh4",
    "minecraft", "javaw", "terraria", "stardewvalley", "hollowknight",
    "celeste", "hades", "cuphead", "ori", "hollowknight",
    "valorant", "valorant-win64-shipping", "cs2", "csgo", "dota2",
    "leagueoflegends", "lol", "overwatch", "overwatch2",
    "apex", "apexlegends", "fortnite", "pubg", "warzone",
    "baldursgate3", "bg3", "starfield", "hogwarts",
    "residentevil", "re4", "re2", "re3", "re7", "re8",
    "dark souls", "darksouls", "sekiro", "bloodborne",
    "monsterhunter", "mhw", "mhrise",
    "zelda", "mario", "metroid", "pokemon",
    "fifa", "nba2k", "madden", "nhl",
    "call of duty", "cod", "mw2", "mw3", "bo6",
    "battlefield", "bf2042", "bf1", "bfv",
    "destiny2", "thewitcher3", "assassinscreed",
    "far cry", "farcry", "watchdogs",
    "tomb raider", "shadowofthetombraider",
    "metro", "metroexodus", "stalker", "stalker2",
    "escape from tarkov", "tarkov",
    "path of exile", "poe", "poe2",
    "diablo", "diablo4", "diablo2",
    "world of warcraft", "wow", "ffxiv", "finalfantasy",
    "genshin", "genshinimpact", "honkai", "starrail",
    "zenless", "zzz",
}

# System processes to exclude from auto-detection
SYSTEM_PROCESSES = {
    "svchost", "csrss", "lsass", "services", "smss", "winlogon",
    "explorer", "dwm", "taskhostw", "sihost", "ctfmon", "conhost",
    "python", "pythonw", "node", "nodejs", "chrome", "brave", "firefox",
    "msedge", "opera", "safari", "iexplore", "code", "devenv",
    "visualstudio", "rider", "pycharm", "idea", "eclipse",
    "notepad", "notepad++", "winword", "excel", "powerpoint",
    "outlook", "teams", "slack", "discord", "telegram",
    "spotify", "vlc", "mpv", "wmplayer", "foobar2000",
    "obs", "obs64", "streamlabs", "xsplit",
    "nvidia", "nvcontainer", "nvdisplay", "nvidia-smi",
    "amd", "radeon", "intel", "igfx",
    "system", "registry", "idle",
    "audiodg", "fontdrvhost", "spoolsv", "searchindexer",
    "searchapp", "startmenuexperiencehost", "shellexperiencehost",
    "runtimebroker", "applicationframehost", "textinputhost",
    "securityhealthservice", "securityhealthsystray",
    "msmpeng", "mpcmdrun", "antimalware",
    "wuauclt", "musnotification", "musnotifyicon",
    "dllhost", "comsurrogate", "wmi", "wmiprvse",
    "taskmgr", "perfmon", "resmon", "mmc",
    "cmd", "powershell", "pwsh", "wt",
    "git", "git-bash", "bash", "sh",
    "java", "javaw", "python3",
    "docker", "dockerd", "com.docker",
    "vmware", "virtualbox", "qemu",
    "steam", "steamwebhelper", "epicgameslauncher", "riotclientservices",
}

# Fullscreen detection (Windows API)
try:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False


def _get_foreground_window_title() -> str:
    if not HAS_WIN32:
        return ""
    try:
        hwnd = _user32.GetForegroundWindow()
        length = _user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
    except Exception:
        pass
    return ""


def _is_fullscreen() -> bool:
    if not HAS_WIN32:
        return False
    try:
        hwnd = _user32.GetForegroundWindow()
        # Get window rect
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        # Get screen dimensions
        screen_w = _user32.GetSystemMetrics(0)  # SM_CXSCREEN
        screen_h = _user32.GetSystemMetrics(1)  # SM_CYSCREEN
        # Check if window covers entire screen
        if (rect.left <= 0 and rect.top <= 0 and
            rect.right >= screen_w and rect.bottom >= screen_h):
            return True
    except Exception:
        pass
    return False


class GamingService:
    """Gaming mode: detection, session tracking, alerts."""

    def __init__(self):
        self.enabled = False
        self.auto_detect = True
        self.gpu_threshold = 30.0       # GPU % sustained
        self.cpu_threshold = 25.0       # CPU % sustained
        self.sustained_seconds = 10     # seconds above threshold
        self.fullscreen_detection = True
        self.game_library: Set[str] = set()  # lowercase exe names
        self.current_session: Optional[Dict] = None
        self._candidates: Dict[str, float] = {}
        self._last_sample_time: float = 0.0
        self._session_peaks: Dict[str, float] = {}
        self._alerts: List[Dict] = []
        self._alert_cooldowns: Dict[str, float] = {}
        self._alert_cooldown_seconds = 60
        # Alert thresholds
        self.gpu_temp_threshold = 80.0
        self.cpu_temp_threshold = 85.0
        self.vram_threshold = 90.0
        self.cpu_usage_threshold = 95.0

    async def initialize(self):
        """Load config from DB or defaults."""
        self.enabled = False
        self._last_sample_time = time.monotonic()
        logger.info("Gaming service initialized (disabled by default)")

    def configure(self, config: Dict[str, Any]):
        """Update gaming config from web panel."""
        self.enabled = config.get("enabled", self.enabled)
        self.auto_detect = config.get("auto_detect", self.auto_detect)
        self.gpu_threshold = config.get("gpu_threshold", self.gpu_threshold)
        self.cpu_threshold = config.get("cpu_threshold", self.cpu_threshold)
        self.sustained_seconds = config.get("sustained_seconds", self.sustained_seconds)
        self.fullscreen_detection = config.get("fullscreen_detection", self.fullscreen_detection)
        self.gpu_temp_threshold = config.get("gpu_temp_threshold", self.gpu_temp_threshold)
        self.cpu_temp_threshold = config.get("cpu_temp_threshold", self.cpu_temp_threshold)
        self.vram_threshold = config.get("vram_threshold", self.vram_threshold)
        if "game_library" in config:
            self.game_library = set(g.lower() for g in config["game_library"])
        logger.info("Gaming config updated: enabled=%s, games=%d", self.enabled, len(self.game_library))

    def get_status(self) -> Dict[str, Any]:
        """Current gaming status."""
        return {
            "enabled": self.enabled,
            "active": self.current_session is not None,
            "session": self.current_session,
            "game_library": sorted(self.game_library),
            "config": {
                "auto_detect": self.auto_detect,
                "gpu_threshold": self.gpu_threshold,
                "cpu_threshold": self.cpu_threshold,
                "sustained_seconds": self.sustained_seconds,
                "fullscreen_detection": self.fullscreen_detection,
                "gpu_temp_threshold": self.gpu_temp_threshold,
                "cpu_temp_threshold": self.cpu_temp_threshold,
                "vram_threshold": self.vram_threshold,
            },
            "alerts": self._alerts[-10:],
        }

    def _find_game_process(self) -> Optional[str]:
        """Find a game process. Returns exe name or None."""
        try:
            foreground_title = _get_foreground_window_title().lower()
            processes = list(psutil.process_iter(["name", "cpu_percent", "memory_info"]))
            
            # Layer 1: Manual game library & known games
            for proc in processes:
                try:
                    raw_name = proc.info.get("name") or ""
                    name = raw_name.lower().replace(".exe", "")
                    if name in self.game_library or name in KNOWN_GAMES:
                        return raw_name
                except Exception:
                    continue

            # Layer 2: Auto-detect via GPU/CPU threshold
            if self.auto_detect:
                now = time.monotonic()
                active_candidates: Dict[str, float] = {}
                for proc in processes:
                    try:
                        raw_name = proc.info.get("name") or ""
                        name = raw_name.lower().replace(".exe", "")
                        if not raw_name or name in SYSTEM_PROCESSES:
                            continue
                        cpu = proc.info.get("cpu_percent") or 0
                        if cpu >= self.cpu_threshold:
                            since = self._candidates.get(raw_name, now)
                            active_candidates[raw_name] = since
                            if now - since >= self.sustained_seconds:
                                if self.fullscreen_detection:
                                    if _is_fullscreen():
                                        self._candidates = active_candidates
                                        return raw_name
                                else:
                                    self._candidates = active_candidates
                                    return raw_name
                    except Exception:
                        continue
                self._candidates = active_candidates
        except Exception as e:
            logger.debug("Game detection error: %s", e)
        return None

    def _sample_stats(self) -> Dict[str, float]:
        """Sample current GPU/CPU/VRAM/temp stats."""
        from app.services.system_monitor import system_monitor
        metrics = system_monitor.get_metrics() or {}
        return {
            "gpu_percent": metrics.get("gpu_percent", 0) or 0,
            "cpu_percent": metrics.get("cpu_percent", 0) or 0,
            "vram_percent": metrics.get("gpu_memory_percent", 0) or 0,
            "vram_used_mb": metrics.get("gpu_memory_used_mb", 0) or 0,
            "gpu_temp": metrics.get("gpu_temp_c", 0) or 0,
            "cpu_temp": metrics.get("cpu_temp_c", 0) or 0,
        }

    def _check_alerts(self, stats: Dict[str, float]):
        """Check alert thresholds and trigger notifications."""
        now = time.monotonic()
        alerts = []
        
        if stats["gpu_temp"] >= self.gpu_temp_threshold:
            key = "gpu_temp"
            if now - self._alert_cooldowns.get(key, 0) > self._alert_cooldown_seconds:
                alerts.append({"type": "gpu_temp", "value": stats["gpu_temp"], "threshold": self.gpu_temp_threshold})
                self._alert_cooldowns[key] = now
        
        if stats["cpu_temp"] >= self.cpu_temp_threshold:
            key = "cpu_temp"
            if now - self._alert_cooldowns.get(key, 0) > self._alert_cooldown_seconds:
                alerts.append({"type": "cpu_temp", "value": stats["cpu_temp"], "threshold": self.cpu_temp_threshold})
                self._alert_cooldowns[key] = now
        
        if stats["vram_percent"] >= self.vram_threshold:
            key = "vram"
            if now - self._alert_cooldowns.get(key, 0) > self._alert_cooldown_seconds:
                alerts.append({"type": "vram", "value": stats["vram_percent"], "threshold": self.vram_threshold})
                self._alert_cooldowns[key] = now
        
        if stats["cpu_percent"] >= self.cpu_usage_threshold:
            key = "cpu_usage"
            if now - self._alert_cooldowns.get(key, 0) > self._alert_cooldown_seconds:
                alerts.append({"type": "cpu_usage", "value": stats["cpu_percent"], "threshold": self.cpu_usage_threshold})
                self._alert_cooldowns[key] = now
        
        for alert in alerts:
            self._alerts.append({
                "type": alert["type"],
                "value": alert["value"],
                "threshold": alert["threshold"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._alerts) > 200:
                self._alerts = self._alerts[-200:]
            # Trigger notification
            try:
                from app.services.notification_service import notification_service
                import asyncio
                title = f"Gaming Alert: {alert['type'].replace('_', ' ').title()}"
                message = f"{alert['type'].replace('_', ' ').title()} at {alert['value']:.1f} (threshold: {alert['threshold']:.1f})"
                asyncio.ensure_future(notification_service.send_notification(
                    title=title, message=message, priority="high", category="gaming"
                ))
            except Exception as e:
                logger.debug("Gaming alert notification failed: %s", e)
        
        # Update peaks
        if self.current_session:
            peaks = self.current_session.setdefault("peaks", {})
            peaks["gpu_percent"] = max(peaks.get("gpu_percent", 0), stats["gpu_percent"])
            peaks["cpu_percent"] = max(peaks.get("cpu_percent", 0), stats["cpu_percent"])
            peaks["vram_percent"] = max(peaks.get("vram_percent", 0), stats["vram_percent"])
            peaks["vram_used_mb"] = max(peaks.get("vram_used_mb", 0), stats["vram_used_mb"])
            peaks["gpu_temp"] = max(peaks.get("gpu_temp", 0), stats["gpu_temp"])
            peaks["cpu_temp"] = max(peaks.get("cpu_temp", 0), stats["cpu_temp"])

    async def tick(self):
        """Called periodically (every 5s) to detect games and track sessions."""
        if not self.enabled:
            return
        
        import asyncio
        now = time.monotonic()
        game_exe = await asyncio.to_thread(self._find_game_process)
        
        if game_exe and self.current_session is None:
            # Game launched
            game_name = game_exe.replace(".exe", "").replace("-", " ").replace("_", " ").title()
            self.current_session = {
                "game_name": game_name,
                "game_exe": game_exe,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "peaks": {},
            }
            self._alerts = []
            logger.info("Gaming session started: %s", game_name)
            # Notify device
            try:
                from app.services.companion import companion_service
                await companion_service.push_notification(
                    title="Gaming Mode",
                    message=f"Session started: {game_name}",
                    priority=1,
                )
            except Exception:
                pass
        
        elif game_exe and self.current_session is not None:
            # Game still running — sample stats
            if now - self._last_sample_time >= 5.0:
                self._last_sample_time = now
                stats = self._sample_stats()
                self._check_alerts(stats)
                if self.current_session:
                    self.current_session["current_stats"] = stats
        
        elif game_exe is None and self.current_session is not None:
            # Game exited
            session = self.current_session
            session["ended_at"] = datetime.now(timezone.utc).isoformat()
            started = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
            ended = datetime.fromisoformat(session["ended_at"].replace("Z", "+00:00"))
            session["duration_seconds"] = int((ended - started).total_seconds())
            logger.info("Gaming session ended: %s (%ds)", session["game_name"], session["duration_seconds"])
            try:
                from app.services.companion import companion_service
                await companion_service.push_notification(
                    title="Gaming Session Ended",
                    message=f"{session['game_name']}: {session['duration_seconds'] // 60}m {session['duration_seconds'] % 60}s",
                    priority=1,
                )
            except Exception:
                pass
            self.current_session = None
            self._candidate_process = None
            self._candidate_since = 0.0

    async def cleanup(self):
        self.enabled = False
        self.current_session = None


# Global instance
gaming_service = GamingService()