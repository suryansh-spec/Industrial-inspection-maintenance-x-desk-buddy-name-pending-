"""
Music Controller Service (yt-music-companion inspired).
Cross-platform music control with YouTube Music API integration.
"""
import asyncio
import logging
import platform
import subprocess
import shlex
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MusicProvider(str, Enum):
    YOUTUBE_MUSIC = "youtube_music"
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"
    LOCAL = "local"
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"


class PlaybackState(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    BUFFERING = "buffering"


class RepeatMode(str, Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


@dataclass
class TrackInfo:
    """Track information."""
    title: str = ""
    artist: str = ""
    album: str = ""
    album_art_url: str = ""
    duration_ms: int = 0
    progress_ms: int = 0
    provider: str = "unknown"
    provider_id: str = ""
    provider_url: str = ""
    is_playing: bool = False


@dataclass
class MusicStatus:
    """Current music playback status."""
    playing: bool = False
    title: str = ""
    artist: str = ""
    album: str = ""
    album_art_url: str = ""
    progress_ms: int = 0
    duration_ms: int = 0
    volume: int = 50
    shuffle: bool = False
    repeat: str = "off"
    provider: str = "unknown"


class MusicController:
    """
    Cross-platform music controller with multiple provider support.
    Inspired by yt-music-companion.
    """
    
    def __init__(self):
        self.initialized = False
        self._provider: Optional[str] = None
        self._player = None
        self._status = MusicStatus()
        self._ytmusic = None
        self._callbacks: Dict[str, callable] = {}
        # Play/pause debounce: track intended state for a few seconds after a command
        self._intended_playing: Optional[bool] = None
        self._intended_until: float = 0.0
        self._explicitly_paused: bool = False
        # Progress interpolation for backgrounded tabs
        self._last_smtc_position_ms: int = 0
        self._last_smtc_read_time: float = 0.0
        
        # Provider availability
        self._providers_available: Dict[str, bool] = {
            "youtube_music": False,
            "spotify": False,
            "apple_music": False,
            "local": True,
            "youtube": True,
        }
    
    async def initialize(self):
        """Initialize music controller and detect available providers."""
        system = platform.system().lower()
        
        # Check for YouTube Music
        try:
            from ytmusicapi import YTMusic
            self._ytmusic = YTMusic()
            self._providers_available["youtube_music"] = True
            logger.info("YouTube Music API available")
        except ImportError:
            logger.warning("ytmusicapi not installed, YouTube Music unavailable")
        except Exception as e:
            logger.warning(f"YouTube Music initialization failed: {e}")
        
        # Check platform-specific providers
        system = platform.system().lower()
        if system == "windows":
            await self._init_windows()
        elif system == "darwin":
            await self._init_macos()
        elif system == "linux":
            await self._init_linux()
        
        # Set default provider — prefer Windows Media Session (SMTC) for live playback status
        if self._providers_available.get("windows_media"):
            self._provider = "windows_media"
        elif self._providers_available.get("wmp"):
            self._provider = "wmp"
        elif self._providers_available["youtube_music"]:
            self._provider = "youtube_music"
        elif self._providers_available["spotify"]:
            self._provider = "spotify"
        elif self._providers_available["apple_music"]:
            self._provider = "apple_music"
        else:
            self._provider = "local"
        
        self.initialized = True
        logger.info(f"Music controller initialized with provider: {self._provider}")
    
    async def _init_windows(self):
        """Initialize Windows media control."""
        try:
            # Try Windows Media Session API via winrt
            import winrt.windows.media.control as media_control
            import winrt.windows.media.playback as playback
            self._providers_available["windows_media"] = True
            logger.info("Windows Media Session API available")
        except ImportError:
            try:
                # Fallback to COM interface
                import win32com.client
                self._player = win32com.client.Dispatch("WMPlayer.OCX.7")
                self._providers_available["wmp"] = True
                logger.info("Windows Media Player COM available")
            except ImportError:
                logger.warning("Windows media control not available")
    
    async def _init_macos(self):
        """Initialize macOS music control."""
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e", 'tell application "Music" to get name of current track'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                self._providers_available["apple_music"] = True
                logger.info("macOS Music app available")
        except Exception:
            logger.warning("macOS Music control not available")
    
    async def _init_linux(self):
        """Initialize Linux music control (MPRIS/playerctl)."""
        try:
            import subprocess
            result = subprocess.run(
                ["playerctl", "status"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                self._providers_available["playerctl"] = True
                logger.info("Linux playerctl available")
        except Exception:
            logger.warning("Linux playerctl not available")
    
    def register_callback(self, event: str, callback):
        """Register callback for music events."""
        self._callbacks[event] = callback
    
    def _emit(self, event: str, data: dict):
        """Emit event to registered callbacks."""
        if event in self._callbacks:
            try:
                self._callbacks[event](data)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")
    
    def get_status(self) -> MusicStatus:
        """Get current playback status."""
        import time
        # If an intended play/pause state is set, fetch SMTC status but
        # override the playing field. Clear the override only when SMTC
        # agrees (so backgrounded tabs don't revert the UI).
        import time as _t
        # Clear the override only when SMTC agrees, or after a long safety timeout.
        if self._intended_playing is not None and _t.monotonic() > self._intended_until:
            self._intended_playing = None
        if self._intended_playing is not None:
            if self._provider in ["windows_media", "wmp"]:
                smtc_status = self._get_windows_status()
            elif self._provider == "youtube_music":
                smtc_status = self._get_ytmusic_status()
            elif self._provider == "apple_music":
                smtc_status = self._get_macos_status()
            elif self._provider == "playerctl":
                smtc_status = self._get_linux_status()
            else:
                smtc_status = self._status
            
            _raw_smtc_playing = smtc_status.playing
            # Intended override takes priority.
            if self._intended_playing is not None:
                _is_playing = self._intended_playing
            else:
                _session_alive = bool(smtc_status.title) and smtc_status.duration_ms > 0
                _not_ended = smtc_status.progress_ms < smtc_status.duration_ms
                _is_playing = (not self._explicitly_paused) and (
                    _raw_smtc_playing or (_session_alive and _not_ended)
                )
            # Interpolate progress for backgrounded tabs (SMTC position freezes).
            if _is_playing is None:
                _session_alive = bool(smtc_status.title) and smtc_status.duration_ms > 0
                _not_ended = smtc_status.progress_ms < smtc_status.duration_ms
                _is_playing = (not self._explicitly_paused) and (
                    smtc_status.playing or (_session_alive and _not_ended)
                )
            smtc_status.playing = _is_playing
            # Interpolate progress for backgrounded tabs (SMTC position freezes).
            if smtc_status.duration_ms > 0 and smtc_status.playing:
                elapsed_ms = int((time.monotonic() - self._last_smtc_read_time) * 1000)
                if smtc_status.progress_ms == self._last_smtc_position_ms and elapsed_ms > 0 and self._last_smtc_position_ms > 0:
                    estimated = self._last_smtc_position_ms + elapsed_ms
                    if estimated < smtc_status.duration_ms:
                        smtc_status.progress_ms = estimated
                    else:
                        smtc_status.progress_ms = smtc_status.duration_ms
            
            # Clear override only when SMTC agrees (use raw, not overridden)
            if self._intended_playing is True and _raw_smtc_playing:
                self._intended_playing = None
            elif self._intended_playing is False and not _raw_smtc_playing:
                self._intended_playing = None
            
            smtc_status.playing = self._intended_playing if self._intended_playing is not None else smtc_status.playing
            return smtc_status
        
        if self._provider == "youtube_music":
            return self._get_ytmusic_status()
        elif self._provider in ["windows_media", "wmp"]:
            status = self._get_windows_status()
            # Heuristic playing state for backgrounded tabs.
            _session_alive = bool(status.title) and status.duration_ms > 0
            _not_ended = status.progress_ms < status.duration_ms
            _is_playing = (not self._explicitly_paused) and (
                status.playing or (_session_alive and _not_ended)
            )
            status.playing = _is_playing
            # Interpolate progress for backgrounded tabs (SMTC position freezes).
            if status.duration_ms > 0 and _is_playing:
                elapsed_ms = int((time.monotonic() - self._last_smtc_read_time) * 1000)
                if status.progress_ms == self._last_smtc_position_ms and elapsed_ms > 0 and self._last_smtc_position_ms > 0:
                    estimated = self._last_smtc_position_ms + elapsed_ms
                    if estimated < status.duration_ms:
                        status.progress_ms = estimated
                    else:
                        status.progress_ms = status.duration_ms
            return status
        elif self._provider == "apple_music":
            return self._get_macos_status()
        elif self._provider == "playerctl":
            return self._get_linux_status()
        
        # Return cached status if provider unavailable
        return self._status
    
    def _get_ytmusic_status(self) -> MusicStatus:
        """Get status from YouTube Music."""
        try:
            if not self._ytmusic:
                return self._status
            
            # Get current playing track
            # Note: ytmusicapi doesn't directly provide playback state
            # This would need a different approach (e.g., browser extension)
            return self._status
        except Exception as e:
            logger.error(f"YTMusic status error: {e}")
            return self._status
    
    def _get_windows_status(self) -> MusicStatus:
        """Get status from Windows Media Session (runs async in thread)."""
        try:
            import winrt.windows.media.control as media_control
            import asyncio
            import concurrent.futures
            
            async def get_media():
                sessions = await media_control.GlobalSystemMediaTransportControlsSessionManager.request_async()
                current = sessions.get_current_session()
                if not current:
                    return None
                
                info = await current.try_get_media_properties_async()
                playback = current.get_playback_info()
                timeline = current.get_timeline_properties()
                
                progress_ms = 0
                try:
                    if timeline and timeline.position:
                        progress_ms = int(timeline.position.total_seconds() * 1000)
                except Exception:
                    pass
                
                duration_ms = 0
                try:
                    if timeline and timeline.end_time:
                        duration_ms = int(timeline.end_time.total_seconds() * 1000)
                except Exception:
                    pass
                
                # Track last known position for interpolation
                import time
                now = time.monotonic()
                import time as _t
                now = _t.monotonic()
                if progress_ms > 0:
                    # Only update the anchor when the position actually changes.
                    # When frozen (backgrounded tab), keep the anchor so elapsed
                    # grows and interpolation can advance the progress.
                    if progress_ms != self._last_smtc_position_ms:
                        self._last_smtc_position_ms = progress_ms
                        self._last_smtc_read_time = now
                    elif self._last_smtc_read_time == 0:
                        self._last_smtc_read_time = now
                
                return {
                    "title": info.title,
                    "artist": info.artist,
                    "album": info.album_title,
                    "playing": str(playback.playback_status).endswith("PLAYING"),
                    "progress": progress_ms,
                    "duration": duration_ms,
                }
            
            # Run in a new event loop in a separate thread to avoid loop conflicts
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, get_media())
                result = future.result(timeout=5)
            
            if result:
                return MusicStatus(
                    playing=result["playing"],
                    title=result["title"] or "",
                    artist=result["artist"] or "",
                    album=result["album"] or "",
                    progress_ms=int(result["progress"]),
                    duration_ms=int(result["duration"]),
                    provider="windows_media",
                )
        except Exception as e:
            logger.error(f"Windows media status error: {e}")
        return self._status
    
    def _get_macos_status(self) -> MusicStatus:
        """Get status from macOS Music app."""
        try:
            import subprocess
            script = '''
            tell application "Music"
                if player state is playing then
                    set trackName to name of current track
                    set artistName to artist of current track
                    set albumName to album of current track
                    set playerPosition to player position
                    set trackDuration to duration of current track
                    return trackName & "|" & artistName & "|" & albumName & "|" & playerPosition & "|" & trackDuration
                else
                    return "STOPPED"
                end if
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip() != "STOPPED":
                parts = result.stdout.strip().split("|")
                if len(parts) >= 5:
                    return MusicStatus(
                        playing=True,
                        title=parts[0],
                        artist=parts[1],
                        album=parts[2],
                        progress_ms=int(float(parts[3]) * 1000),
                        duration_ms=int(float(parts[4]) * 1000)
                    )
        except Exception as e:
            logger.error(f"macOS music status error: {e}")
        return self._status
    
    def _get_linux_status(self) -> MusicStatus:
        """Get status from Linux playerctl."""
        try:
            import subprocess
            result = subprocess.run(
                ["playerctl", "metadata", "--format", "{{title}}|{{artist}}|{{album}}|{{duration}}|{{position}}"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("|")
                if len(parts) >= 5:
                    return MusicStatus(
                        playing=True,
                        title=parts[0] or "",
                        artist=parts[1] or "",
                        album=parts[2] or "",
                        duration_ms=int(float(parts[3])) * 1000 if parts[3] else 0,
                        progress_ms=int(float(parts[4])) * 1000 if parts[4] else 0,
                    )
        except Exception as e:
            logger.error(f"Linux playerctl error: {e}")
        return self._status
    
    async def play(self):
        """Play/resume music."""
        if self._provider == "youtube_music":
            # Would need browser extension or web control
            pass
        elif self._provider in ["windows_media", "wmp"]:
            await self._play_windows()
        elif self._provider == "apple_music":
            await self._play_macos()
        elif self._provider == "playerctl":
            await self._play_linux()
        
        self._status.playing = True
        import time
        self._intended_playing = True
        self._intended_until = time.monotonic() + 30.0
        self._explicitly_paused = False
        self._emit("play", {})
    
    async def _play_windows(self):
        try:
            import winrt.windows.media.control as media_control
            import asyncio
            import concurrent.futures

            async def do_play():
                mgr = await media_control.GlobalSystemMediaTransportControlsSessionManager.request_async()
                current = mgr.get_current_session()
                if current:
                    await current.try_play_async()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, do_play())
                future.result(timeout=5)
        except Exception:
            # Fallback to media key
            import subprocess
            subprocess.run(
                ["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys([char]179)"],
                check=False
            )
    
    async def _play_macos(self):
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Music" to play'], check=False)
    
    async def _play_linux(self):
        import subprocess
        subprocess.run(["playerctl", "play"], check=False)
    
    async def pause(self):
        """Pause music."""
        if self._provider in ["windows_media", "wmp"]:
            await self._pause_windows()
        elif self._provider == "apple_music":
            await self._pause_macos()
        elif self._provider == "playerctl":
            await self._pause_linux()
        
        self._status.playing = False
        import time
        self._intended_playing = False
        self._intended_until = time.monotonic() + 30.0
        self._explicitly_paused = True
        self._emit("pause", {})
    
    async def _pause_windows(self):
        try:
            import winrt.windows.media.control as media_control
            import asyncio
            import concurrent.futures

            async def do_pause():
                mgr = await media_control.GlobalSystemMediaTransportControlsSessionManager.request_async()
                current = mgr.get_current_session()
                if current:
                    await current.try_pause_async()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, do_pause())
                future.result(timeout=5)
        except Exception:
            import subprocess
            subprocess.run(
                ["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys([char]179)"],
                check=False
            )
    
    async def _pause_macos(self):
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Music" to pause'], check=False)
    
    async def _pause_linux(self):
        import subprocess
        subprocess.run(["playerctl", "pause"], check=False)
    
    async def next_track(self):
        """Skip to next track."""
        if self._provider in ["windows_media", "wmp"]:
            await self._next_windows()
        elif self._provider == "apple_music":
            await self._next_macos()
        elif self._provider == "playerctl":
            await self._next_linux()
    
    async def _next_windows(self):
        try:
            import winrt.windows.media.control as media_control
            import asyncio
            import concurrent.futures

            async def do_next():
                mgr = await media_control.GlobalSystemMediaTransportControlsSessionManager.request_async()
                current = mgr.get_current_session()
                if current:
                    await current.try_skip_next_async()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, do_next())
                future.result(timeout=5)
        except Exception:
            import subprocess
            subprocess.run(
                ["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys([char]176)"],
                check=False
            )
    
    async def _next_macos(self):
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Music" to next track'], check=False)
    
    async def _next_linux(self):
        import subprocess
        subprocess.run(["playerctl", "next"], check=False)
    
    async def previous_track(self):
        """Go to previous track."""
        if self._provider in ["windows_media", "wmp"]:
            await self._prev_windows()
        elif self._provider == "apple_music":
            await self._prev_macos()
        elif self._provider == "playerctl":
            await self._prev_linux()
    
    async def _prev_windows(self):
        try:
            import winrt.windows.media.control as media_control
            import asyncio
            import concurrent.futures

            async def do_prev():
                mgr = await media_control.GlobalSystemMediaTransportControlsSessionManager.request_async()
                current = mgr.get_current_session()
                if current:
                    await current.try_skip_previous_async()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, do_prev())
                future.result(timeout=5)
        except Exception:
            import subprocess
            subprocess.run(
                ["powershell", "-c", "(New-Object -ComObject WScript.Shell).SendKeys([char]177)"],
                check=False
            )
    
    async def _prev_macos(self):
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Music" to previous track'], check=False)
    
    async def _prev_linux(self):
        import subprocess
        subprocess.run(["playerctl", "previous"], check=False)
    
    async def set_volume(self, level: int):
        """Set volume (0-100)."""
        if level < 0: level = 0
        if level > 100: level = 100
        
        try:
            system = platform.system().lower()
            if system == "windows":
                import subprocess
                subprocess.run([
                    "powershell", "-c",
                    f"(New-Object -ComObject WScript.Shell).SendKeys([char]([int]('{level}' + '0')))"
                ], check=False)
            elif system == "darwin":
                import subprocess
                subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=False)
            elif system == "linux":
                import subprocess
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=False)
        except Exception as e:
            logger.error(f"Volume error: {e}")
    
    def get_available_providers(self) -> dict:
        """Get list of available providers."""
        return {
            "current": self._provider,
            "available": self._providers_available
        }
    
    async def search_youtube_music(self, query: str, limit: int = 10) -> List[Dict]:
        """Search YouTube Music."""
        if not self._ytmusic:
            return []
        
        try:
            results = self._ytmusic.search(query, filter="songs", limit=limit)
            return [
                {
                    "title": r.get("title", ""),
                    "artist": ", ".join([a["name"] for a in r.get("artists", [])]),
                    "album": r.get("album", {}).get("name", "") if r.get("album") else "",
                    "duration": r.get("duration", ""),
                    "video_id": r.get("videoId", ""),
                    "thumbnail": r.get("thumbnails", [{}])[0].get("url", "") if r.get("thumbnails") else "",
                    "provider": "youtube_music",
                    "provider_id": r.get("videoId", "")
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"YouTube Music search error: {e}")
            return []
    
    def get_lyrics(self, video_id: str) -> Optional[str]:
        """Get lyrics for a YouTube Music track."""
        if not self._ytmusic:
            return None
        try:
            lyrics = self._ytmusic.get_lyrics(video_id)
            return lyrics.get("lyrics") if lyrics else None
        except Exception as e:
            logger.error(f"Lyrics fetch error: {e}")
            return None
    
    def get_queue(self) -> List[Dict]:
        """Get current queue."""
        # Would need integration with actual player
        return []
    
    def add_to_queue(self, video_id: str) -> bool:
        """Add track to queue."""
        # Implementation depends on provider
        return False
    
    async def cleanup(self):
        """Cleanup resources."""
        self.initialized = False


# Global instance
music_controller = MusicController()