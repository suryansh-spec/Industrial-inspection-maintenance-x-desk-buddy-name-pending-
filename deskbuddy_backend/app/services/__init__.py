"""
Services package for DeskBuddy Backend.
"""
from app.services.system_monitor import system_monitor, SystemMonitor, GPUMetrics, SystemMetricsSnapshot
from app.services.notification_service import notification_service, NotificationService
from app.services.music import music_controller, MusicController, TrackInfo, MusicStatus
from app.services.gaming import gaming_service, GamingService
from app.services.calendar import calendar_service, CalendarService, CalendarEvent
from app.services.voice import voice_assistant, VoiceAssistant
from app.services.hardware_bridge import hardware_bridge, HardwareBridge, SensorData, DeviceCommand
from app.services.deskmate import DeskMateService, create_deskbuddy_services

__all__ = [
    "system_monitor",
    "SystemMonitor",
    "GPUMetrics",
    "SystemMetricsSnapshot",
    "notification_service",
    "NotificationService",
    "music_controller",
    "MusicController",
    "TrackInfo",
    "MusicStatus",
    "calendar_service",
    "CalendarService",
    "CalendarEvent",
    "voice_assistant",
    "VoiceAssistant",
    "hardware_bridge",
    "HardwareBridge",
    "SensorData",
    "DeviceCommand",
    "DeskMateService",
    "create_deskbuddy_services",
    "gaming_service",
    "GamingService",
]