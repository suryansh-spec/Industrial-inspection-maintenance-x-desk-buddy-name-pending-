"""
DeskMate-inspired Desktop Companion Module
Inspired by https://github.com/Kamalbura/DeskMate

Features:
- System tray integration with context menu
- Always-on-top overlay widget
- Keyboard shortcuts/hotkeys
- Notification center with history
- Quick actions / shortcuts panel
- Pomodoro timer
- Clipboard history
- Window management shortcuts
- Customizable themes
"""
import asyncio
import json
import logging
import platform
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import os
import sys

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class DeskMateNotification:
    id: str
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    read: bool = False
    actions: List[Dict] = field(default_factory=list)
    category: str = "general"
    expires_at: Optional[datetime] = None


@dataclass
class QuickAction:
    id: str
    label: str
    icon: str
    action: Callable
    hotkey: Optional[str] = None
    category: str = "general"
    enabled: bool = True


@dataclass
class PomodoroSession:
    work_duration: int = 25 * 60  # seconds
    break_duration: int = 5 * 60
    long_break_duration: int = 15 * 60
    sessions_before_long_break: int = 4
    current_session: int = 0
    is_running: bool = False
    is_break: bool = False
    time_remaining: int = 0
    on_tick: Optional[Callable] = None
    on_complete: Optional[Callable] = None


class DeskMateService:
    """
    DeskMate-inspired Desktop Companion Service

    Features:
    - System tray integration
    - Overlay widget (always on top)
    - Notification center with history
    - Quick actions panel
    - Pomodoro timer
    - Clipboard history
    - Global hotkeys
    - Window management
    - Theme support
    """

    def __init__(self):
        self.running = False
        self.notifications: List[DeskMateNotification] = []
        self.quick_actions: List[QuickAction] = []
        self.clipboard_history: List[str] = []
        self.max_clipboard_items = 50
        self.pomodoro = PomodoroSession()
        self.hotkeys: Dict[str, Callable] = {}
        self.theme = "dark"  # dark, light, auto
        self.widget_visible = True
        self.widget_position = "top-right"
        self.settings = self._load_settings()

        # Callbacks for UI updates
        self.on_notification: Optional[Callable] = None
        self.on_clipboard_change: Optional[Callable] = None
        self.on_pomodoro_tick: Optional[Callable] = None
        self.on_pomodoro_complete: Optional[Callable] = None

    def _load_settings(self) -> dict:
        """Load settings from config file."""
        settings_path = os.path.expanduser("~/.config/deskbuddy/deskmate_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "theme": "dark",
            "widget_position": "top-right",
            "widget_opacity": 0.95,
            "notifications_enabled": True,
            "hotkeys_enabled": True,
            "start_minimized": False,
            "auto_start_pomodoro": False
        }

    def _save_settings(self):
        """Save settings to config file."""
        settings_path = os.path.expanduser("~/.config/deskbuddy/deskmate_settings.json")
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        try:
            with open(settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    # ========================================================================
    # NOTIFICATION CENTER
    # ========================================================================

    def add_notification(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        category: str = "general",
        actions: List[Dict] = None,
        expires_in: Optional[int] = None
    ) -> DeskMateNotification:
        """Add a new notification."""
        notification = DeskMateNotification(
            id=f"notif_{int(time.time() * 1000)}",
            title=title,
            message=message,
            priority=priority,
            category=category,
            actions=actions or [],
            expires_at=datetime.now() + timedelta(seconds=expires_in) if expires_in else None
        )

        self.notifications.append(notification)

        # Trim old notifications
        if len(self.notifications) > 100:
            self.notifications = self.notifications[-100:]

        # Trigger callback
        if self.on_notification:
            self.on_notification(notification)

        logger.info(f"Notification: {title} - {message}")
        return notification

    def mark_read(self, notification_id: str):
        """Mark notification as read."""
        for n in self.notifications:
            if n.id == notification_id:
                n.read = True
                break

    def dismiss(self, notification_id: str):
        """Dismiss/remove notification."""
        self.notifications = [n for n in self.notifications if n.id != notification_id]

    def clear_all(self, category: Optional[str] = None):
        """Clear all notifications, optionally filtered by category."""
        if category:
            self.notifications = [n for n in self.notifications if n.category != category]
        else:
            self.notifications.clear()

    def get_notifications(
        self,
        unread_only: bool = False,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[DeskMateNotification]:
        """Get notifications with filtering."""
        result = self.notifications
        if unread_only:
            result = [n for n in result if not n.read]
        if category:
            result = [n for n in result if n.category == category]
        return sorted(result, key=lambda x: x.timestamp, reverse=True)[:limit]

    def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        return sum(1 for n in self.notifications if not n.read)

    # ========================================================================
    # QUICK ACTIONS
    # ========================================================================

    def register_action(self, action: QuickAction):
        """Register a quick action."""
        self.quick_actions.append(action)
        self.quick_actions.sort(key=lambda x: x.category)

    def unregister_action(self, action_id: str):
        """Unregister a quick action."""
        self.quick_actions = [a for a in self.quick_actions if a.id != action_id]

    def get_actions(self, category: Optional[str] = None) -> List[QuickAction]:
        """Get quick actions, optionally filtered by category."""
        actions = self.quick_actions
        if category:
            actions = [a for a in actions if a.category == category]
        return [a for a in actions if a.enabled]

    def execute_action(self, action_id: str) -> Any:
        """Execute a quick action by ID."""
        for action in self.quick_actions:
            if action.id == action_id and action.enabled:
                try:
                    return action.action()
                except Exception as e:
                    logger.error(f"Action {action_id} failed: {e}")
                    return {"error": str(e)}
        return {"error": "Action not found"}

    # ========================================================================
    # CLIPBOARD HISTORY
    # ========================================================================

    def add_to_clipboard_history(self, text: str):
        """Add text to clipboard history."""
        if not text or text in self.clipboard_history:
            return

        self.clipboard_history.insert(0, text)
        if len(self.clipboard_history) > self.max_clipboard_items:
            self.clipboard_history = self.clipboard_history[:self.max_clipboard_items]

        if self.on_clipboard_change:
            self.on_clipboard_change(self.clipboard_history)

    def get_clipboard_history(self, limit: int = 20) -> List[str]:
        """Get clipboard history."""
        return self.clipboard_history[:limit]

    def clear_clipboard_history(self):
        """Clear clipboard history."""
        self.clipboard_history.clear()
        if self.on_clipboard_change:
            self.on_clipboard_change([])

    # ========================================================================
    # POMODORO TIMER
    # ========================================================================

    def start_pomodoro(self):
        """Start Pomodoro timer."""
        if self.pomodoro.is_running:
            return

        self.pomodoro.is_running = True
        self.pomodoro.is_break = False
        self.pomodoro.time_remaining = self.pomodoro.work_duration
        self._pomodoro_task = asyncio.create_task(self._pomodoro_loop())
        logger.info("Pomodoro started")

    def pause_pomodoro(self):
        """Pause Pomodoro timer."""
        self.pomodoro.is_running = False
        if hasattr(self, '_pomodoro_task'):
            self._pomodoro_task.cancel()
        logger.info("Pomodoro paused")

    def reset_pomodoro(self):
        """Reset Pomodoro timer."""
        self.pause_pomodoro()
        self.pomodoro.current_session = 0
        self.pomodoro.time_remaining = self.pomodoro.work_duration
        self.pomodoro.is_break = False
        logger.info("Pomodoro reset")

    async def _pomodoro_loop(self):
        """Pomodoro timer loop."""
        while self.pomodoro.is_running and self.pomodoro.time_remaining > 0:
            await asyncio.sleep(1)
            self.pomodoro.time_remaining -= 1

            if self.on_pomodoro_tick:
                self.on_pomodoro_tick(self.pomodoro.time_remaining, self.pomodoro.is_break)

        if self.pomodoro.is_running:
            # Session complete
            await self._pomodoro_complete()

    async def _pomodoro_complete(self):
        """Handle Pomodoro session completion."""
        if self.pomodoro.is_break:
            # Break finished, start work session
            self.pomodoro.is_break = False
            self.pomodoro.time_remaining = self.pomodoro.work_duration
            self.pomodoro.current_session += 1

            self.add_notification(
                "Break Over",
                "Time to focus! Starting work session.",
                NotificationPriority.HIGH,
                "pomodoro"
            )

            if self.on_pomodoro_complete:
                self.on_pomodoro_complete("work_started")
        else:
            # Work session finished
            self.pomodoro.current_session += 1

            if self.pomodoro.current_session % self.pomodoro.sessions_before_long_break == 0:
                # Long break
                self.pomodoro.is_break = True
                self.pomodoro.time_remaining = self.pomodoro.long_break_duration
                self.add_notification(
                    "Long Break!",
                    f"Great work! Take a {self.pomodoro.long_break_duration//60} minute break.",
                    NotificationPriority.HIGH,
                    "pomodoro"
                )
            else:
                # Short break
                self.pomodoro.is_break = True
                self.pomodoro.time_remaining = self.pomodoro.break_duration
                self.add_notification(
                    "Break Time!",
                    f"Take a {self.pomodoro.break_duration//60} minute break.",
                    NotificationPriority.NORMAL,
                    "pomodoro"
                )

            if self.on_pomodoro_complete:
                self.on_pomodoro_complete("break_started" if self.pomodoro.is_break else "work_completed")

        # Continue if still running
        if self.pomodoro.is_running:
            self._pomodoro_task = asyncio.create_task(self._pomodoro_loop())

    def get_pomodoro_status(self) -> dict:
        """Get current Pomodoro status."""
        return {
            "is_running": self.pomodoro.is_running,
            "is_break": self.pomodoro.is_break,
            "time_remaining": self.pomodoro.time_remaining,
            "current_session": self.pomodoro.current_session,
            "sessions_before_long_break": self.pomodoro.sessions_before_long_break,
            "work_duration": self.pomodoro.work_duration,
            "break_duration": self.pomodoro.break_duration,
            "long_break_duration": self.pomodoro.long_break_duration
        }

    # ========================================================================
    # HOTKEYS
    # ========================================================================

    def register_hotkey(self, key: str, callback: Callable):
        """Register a global hotkey."""
        self.hotkeys[key] = callback
        logger.info(f"Registered hotkey: {key}")

    def unregister_hotkey(self, key: str):
        """Unregister a hotkey."""
        if key in self.hotkeys:
            del self.hotkeys[key]

    # ========================================================================
    # WIDGET / OVERLAY
    # ========================================================================

    def set_widget_visibility(self, visible: bool):
        """Toggle widget visibility."""
        self.widget_visible = visible
        self.settings["widget_visible"] = visible
        self._save_settings()

    def set_widget_position(self, position: str):
        """Set widget position (top-left, top-right, bottom-left, bottom-right, center)."""
        valid = ["top-left", "top-right", "bottom-left", "bottom-right", "center"]
        if position in valid:
            self.widget_position = position
            self.settings["widget_position"] = position
            self._save_settings()

    def set_theme(self, theme: str):
        """Set theme (dark, light, auto)."""
        if theme in ["dark", "light", "auto"]:
            self.theme = theme
            self.settings["theme"] = theme
            self._save_settings()

    # ========================================================================
    # SYSTEM TRAY (placeholder - requires platform-specific implementation)
    # ========================================================================

    def create_system_tray(self):
        """Create system tray icon (platform-specific)."""
        system = platform.system().lower()

        if system == "windows":
            return self._create_windows_tray()
        elif system == "darwin":
            return self._create_macos_tray()
        elif system == "linux":
            return self._create_linux_tray()

        return None

    def _create_windows_tray(self):
        """Create Windows system tray using pystray."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Create simple icon
            image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle([16, 16, 48, 48], fill=(0, 122, 255))
            draw.text((20, 20), "DB", fill=(255, 255, 255))

            menu = pystray.Menu(
                pystray.MenuItem("Show/Hide Widget", self._toggle_widget),
                pystray.MenuItem("Pomodoro", self._pomodoro_menu),
                pystray.MenuItem("Quick Actions", self._quick_actions_menu),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._quit_app)
            )

            icon = pystray.Icon("deskbuddy", image, "DeskBuddy", menu)
            return icon
        except ImportError:
            logger.warning("pystray not installed, system tray unavailable")
            return None

    def _create_macos_tray(self):
        """Create macOS menu bar item."""
        try:
            import rumps

            class DeskBuddyApp(rumps.App):
                def __init__(self, deskmate_service):
                    super().__init__("DeskBuddy")
                    self.service = deskmate_service
                    self.menu = [
                        rumps.MenuItem("Show/Hide Widget", callback=self._toggle_widget),
                        rumps.MenuItem("Pomodoro", callback=self._pomodoro_menu),
                        None,
                        rumps.MenuItem("Quit", callback=self._quit_app)
                    ]

            app = DeskBuddyApp(self)
            return app
        except ImportError:
            logger.warning("rumps not installed, macOS tray unavailable")
            return None

    def _create_linux_tray(self):
        """Create Linux system tray."""
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            gi.require_version('AppIndicator3', '0.1')
            from gi.repository import Gtk, AppIndicator3

            indicator = AppIndicator3.Indicator.new(
                "deskbuddy",
                "applications-accessories",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

            menu = Gtk.Menu()

            show_item = Gtk.MenuItem(label="Show/Hide Widget")
            show_item.connect("activate", lambda _: self._toggle_widget())
            menu.append(show_item)

            quit_item = Gtk.MenuItem(label="Quit")
            quit_item.connect("activate", lambda _: Gtk.main_quit())
            menu.append(quit_item)

            menu.show_all()
            indicator.set_menu(menu)

            return indicator
        except Exception as e:
            logger.warning(f"Linux tray unavailable: {e}")
            return None

    def _toggle_widget(self, *args):
        """Toggle widget visibility."""
        self.set_widget_visibility(not self.widget_visible)

    def _pomodoro_menu(self, *args):
        """Show Pomodoro submenu."""
        pass  # Implement submenu

    def _quick_actions_menu(self, *args):
        """Show quick actions menu."""
        pass

    def _quit_app(self, *args):
        """Quit application."""
        import sys
        sys.exit(0)

    # ========================================================================
    # WINDOW MANAGEMENT (Windows)
    # ========================================================================

    def get_window_list(self) -> List[Dict]:
        """Get list of open windows (Windows)."""
        if platform.system().lower() != "windows":
            return []

        try:
            import win32gui

            windows = []

            def enum_windows(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        rect = win32gui.GetWindowRect(hwnd)
                        results.append({
                            "hwnd": hwnd,
                            "title": title,
                            "rect": rect
                        })
                return True

            win32gui.EnumWindows(enum_windows, windows)
            return windows
        except ImportError:
            return []

    def minimize_all(self):
        """Minimize all windows (Windows)."""
        if platform.system().lower() == "windows":
            import win32gui
            import win32con

            def minimize(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return True
            win32gui.EnumWindows(minimize, None)

    def restore_all(self):
        """Restore minimized windows."""
        if platform.system().lower() == "windows":
            import win32gui
            import win32con

            def restore(hwnd, _):
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                return True
            win32gui.EnumWindows(restore, None)


# ========================================================================
# INTEGRATION WITH EXISTING DESKTOP BRIDGE
# ========================================================================

class DeskMateIntegration:
    """
    Integration layer between DeskMate and existing Desktop Bridge.
    """

    def __init__(self, deskmate: DeskMateService, bridge_services: dict):
        self.deskmate = deskmate
        self.services = bridge_services
        self._setup_default_actions()
        self._setup_hotkeys()

    def _setup_default_actions(self):
        """Register default quick actions."""
        actions = [
            QuickAction(
                id="toggle_widget",
                label="Toggle Widget",
                icon="🖼️",
                action=lambda: self.deskmate.set_widget_visibility(not self.deskmate.widget_visible),
                hotkey="ctrl+alt+w",
                category="window"
            ),
            QuickAction(
                id="start_pomodoro",
                label="Start Pomodoro",
                icon="🍅",
                action=lambda: self.deskmate.start_pomodoro(),
                hotkey="ctrl+alt+p",
                category="productivity"
            ),
            QuickAction(
                id="pause_pomodoro",
                label="Pause Pomodoro",
                icon="⏸️",
                action=lambda: self.deskmate.pause_pomodoro(),
                hotkey="ctrl+alt+shift+p",
                category="productivity"
            ),
            QuickAction(
                id="get_device_status",
                label="Device Status",
                icon="📱",
                action=lambda: self._get_device_status(),
                hotkey="ctrl+alt+d",
                category="device"
            ),
            QuickAction(
                id="run_inspection",
                label="Run Inspection",
                icon="🔍",
                action=lambda: self._run_inspection(),
                hotkey="ctrl+alt+i",
                category="inspection"
            ),
            QuickAction(
                id="play_music",
                label="Play Music",
                icon="▶️",
                action=lambda: self._control_music("play"),
                hotkey="ctrl+alt+m",
                category="media"
            ),
            QuickAction(
                id="pause_music",
                label="Pause Music",
                icon="⏸️",
                action=lambda: self._control_music("pause"),
                hotkey="ctrl+alt+shift+m",
                category="media"
            ),
            QuickAction(
                id="next_track",
                label="Next Track",
                icon="⏭️",
                action=lambda: self._control_music("next"),
                hotkey="ctrl+alt+n",
                category="media"
            ),
            QuickAction(
                id="show_notifications",
                label="Notifications",
                icon="🔔",
                action=lambda: self._show_notifications(),
                hotkey="ctrl+alt+n",
                category="general"
            ),
        ]

        for action in actions:
            self.deskmate.register_action(action)

    def _setup_hotkeys(self):
        """Register global hotkeys."""
        # Hotkeys are registered via the quick actions
        # Platform-specific implementation needed for actual global hotkey registration
        pass

    async def _get_device_status(self):
        """Get device status from serial manager."""
        from desktop_bridge.main import serial_manager
        if serial_manager and serial_manager.is_connected:
            return {"connected": True, "port": serial_manager.port}
        return {"connected": False}

    async def _run_inspection(self):
        """Trigger inspection on device."""
        from desktop_bridge.main import serial_manager
        if serial_manager and serial_manager.is_connected:
            await serial_manager.send_command("start_inspection", {"method": "auto"})
            return {"status": "started"}
        return {"error": "Device not connected"}

    async def _control_music(self, action: str):
        """Control music playback."""
        from desktop_bridge.main import music_controller
        if music_controller and music_controller.initialized:
            if action == "play":
                await music_controller.play()
            elif action == "pause":
                await music_controller.pause()
            elif action == "next":
                await music_controller.next_track()
            elif action == "previous":
                await music_controller.previous_track()
            return {"status": "ok"}
        return {"error": "Music control not available"}

    async def _show_notifications(self):
        """Show notifications panel."""
        notifications = self.deskmate.get_notifications(unread_only=True, limit=10)
        return {"notifications": [n.to_dict() if hasattr(n, 'to_dict') else n.__dict__ for n in notifications]}


# ========================================================================
# FACTORY FUNCTION
# ========================================================================

def create_deskbuddy_services() -> dict:
    """
    Create all DeskBuddy services with DeskMate integration.

    Returns dict with all services ready to use.
    """
    # Create core services
    deskmate = DeskMateService()

    # Initialize with existing bridge services
    bridge_services = {
        "serial_manager": None,  # Set by main
        "pc_monitor": None,
        "music_controller": None,
        "calendar_service": None,
    }

    integration = DeskMateIntegration(deskmate, bridge_services)

    # Connect DeskMate callbacks to bridge
    deskmate.on_notification = lambda n: broadcast_notification(n)
    deskmate.on_pomodoro_tick = lambda rem, is_break: broadcast_pomodoro(rem, is_break)
    deskmate.on_pomodoro_complete = lambda event: broadcast_pomodoro_event(event)
    deskmate.on_clipboard_change = lambda history: broadcast_clipboard(history)

    return {
        "deskmate": deskmate,
        "integration": integration,
        "bridge_services": bridge_services
    }


def broadcast_notification(notification: DeskMateNotification):
    """Broadcast notification via WebSocket."""
    from desktop_bridge.main import ws_manager
    asyncio.create_task(ws_manager.broadcast("notifications", {
        "type": "notification",
        "data": {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority.value,
            "category": notification.category,
            "timestamp": notification.timestamp.isoformat(),
            "actions": notification.actions
        }
    }))


def broadcast_pomodoro(remaining: int, is_break: bool):
    """Broadcast Pomodoro tick."""
    from desktop_bridge.main import ws_manager
    asyncio.create_task(ws_manager.broadcast("pomodoro", {
        "type": "tick",
        "remaining": remaining,
        "is_break": is_break
    }))


def broadcast_pomodoro_event(event: str):
    """Broadcast Pomodoro completion event."""
    from desktop_bridge.main import ws_manager
    asyncio.create_task(ws_manager.broadcast("pomodoro", {
        "type": "complete",
        "event": event
    }))


def broadcast_clipboard(history: list):
    """Broadcast clipboard history update."""
    from desktop_bridge.main import ws_manager
    asyncio.create_task(ws_manager.broadcast("clipboard", {
        "type": "history_update",
        "data": history
    }))