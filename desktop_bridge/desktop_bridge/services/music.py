"""
Music Controller - Controls music playback (Windows Media, Spotify, etc.)
"""
import asyncio
import logging
from typing import Optional, Dict, Any
import platform

logger = logging.getLogger(__name__)


class MusicController:
    """Controls music playback on Windows."""
    
    def __init__(self):
        self.initialized = False
        self._player = None
        self._status = {
            "playing": False,
            "title": None,
            "artist": None,
            "album": None,
            "progress_ms": 0,
            "duration_ms": 0,
            "volume": 50,
            "shuffle": False,
            "repeat": "off"
        }
    
    async def initialize(self):
        """Initialize music controller."""
        system = platform.system().lower()
        
        if system == "windows":
            await self._init_windows()
        elif system == "darwin":
            await self._init_macos()
        elif system == "linux":
            await self._init_linux()
        else:
            logger.warning(f"Music control not supported on {system}")
            return
        
        self.initialized = True
        logger.info("Music controller initialized")
    
    async def _init_windows(self):
        """Initialize Windows media control."""
        try:
            # Try to use Windows Media Session API via winrt
            import winrt.windows.media.control as media_control
            import winrt.windows.media.playback as playback
            
            self._player = media_control.GlobalSystemMediaTransportControlsSessionManager
            logger.info("Windows Media Session API available")
        except ImportError:
            # Fallback to keyboard simulation or COM
            try:
                import win32com.client
                self._player = win32com.client.Dispatch("WMPlayer.OCX.7")
                logger.info("Windows Media Player COM available")
            except ImportError:
                logger.warning("No Windows media control available, using mock")
    
    async def _init_macos(self):
        """Initialize macOS music control."""
        try:
            import subprocess
            # Test AppleScript
            result = subprocess.run(
                ["osascript", "-e", 'tell application "Music" to get name of current track'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.info("macOS Music app available")
        except Exception:
            logger.warning("macOS Music control not available")
    
    async def _init_linux(self):
        """Initialize Linux music control (MPRIS/DBus)."""
        try:
            import subprocess
            result = subprocess.run(
                ["playerctl", "status"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                logger.info("Linux playerctl available")
        except Exception:
            logger.warning("Linux music control not available")
    
    async def cleanup(self):
        """Cleanup resources."""
        self.initialized = False
    
    def get_status(self) -> dict:
        """Get current playback status."""
        if not self.initialized:
            return self._status
        
        # In a real implementation, this would query the actual player
        return self._status
    
    async def play(self):
        """Play/resume music."""
        if not self.initialized:
            self._status["playing"] = True
            return
        
        try:
            system = platform.system().lower()
            if system == "windows":
                await self._play_windows()
            elif system == "darwin":
                await self._play_macos()
            elif system == "linux":
                await self._play_linux()
            
            self._status["playing"] = True
        except Exception as e:
            logger.error(f"Play error: {e}")
    
    async def _play_windows(self):
        """Play on Windows."""
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-c", 
                 "(New-Object -ComObject WScript.Shell).SendKeys([char]179)"],
                check=False
            )  # VK_MEDIA_PLAY_PAUSE
        except Exception:
            pass
    
    async def _play_macos(self):
        """Play on macOS."""
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Music" to play'], check=False)
    
    async def _play_linux(self):
        """Play on Linux."""
        import subprocess
        subprocess.run(["playerctl", "play"], check=False)
    
    async def pause(self):
        """Pause music."""
        try:
            system = platform.system().lower()
            if system == "windows":
                import subprocess
                subprocess.run(
                    ["powershell", "-c", 
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]179)"],
                    check=False
                )
            elif system == "darwin":
                import subprocess
                subprocess.run(["osascript", "-e", 'tell application "Music" to pause'], check=False)
            elif system == "linux":
                import subprocess
                subprocess.run(["playerctl", "pause"], check=False)
            
            self._status["playing"] = False
        except Exception as e:
            logger.error(f"Pause error: {e}")
    
    async def next_track(self):
        """Next track."""
        try:
            system = platform.system().lower()
            if system == "windows":
                import subprocess
                subprocess.run(
                    ["powershell", "-c", 
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]176)"],
                    check=False
                )  # VK_MEDIA_NEXT_TRACK
            elif system == "darwin":
                import subprocess
                subprocess.run(["osascript", "-e", 'tell application "Music" to next track'], check=False)
            elif system == "linux":
                import subprocess
                subprocess.run(["playerctl", "next"], check=False)
        except Exception as e:
            logger.error(f"Next track error: {e}")
    
    async def previous_track(self):
        """Previous track."""
        try:
            system = platform.system().lower()
            if system == "windows":
                import subprocess
                subprocess.run(
                    ["powershell", "-c", 
                     "(New-Object -ComObject WScript.Shell).SendKeys([char]177)"],
                    check=False
                )  # VK_MEDIA_PREV_TRACK
            elif system == "darwin":
                import subprocess
                subprocess.run(["osascript", "-e", 'tell application "Music" to previous track'], check=False)
            elif system == "linux":
                import subprocess
                subprocess.run(["playerctl", "previous"], check=False)
        except Exception as e:
            logger.error(f"Previous track error: {e}")
    
    async def set_volume(self, level: int):
        """Set volume (0-100)."""
        if not 0 <= level <= 100:
            raise ValueError("Volume must be 0-100")
        
        self._status["volume"] = level
        
        try:
            system = platform.system().lower()
            if system == "windows":
                import subprocess
                # Set system volume via PowerShell
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
    
    async def get_current_track(self) -> Optional[dict]:
        """Get current track info (if available)."""
        # Would query actual player
        return {
            "title": self._status.get("title"),
            "artist": self._status.get("artist"),
            "album": self._status.get("album")
        }