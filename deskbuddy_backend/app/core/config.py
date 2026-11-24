"""
Configuration management for DeskBuddy Backend.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional, List
from pydantic import Field


class Settings(BaseSettings):
    # Application
    app_name: str = "DeskBuddy Backend"
    version: str = "1.0.0"
    debug: bool = True
    api_prefix: str = "/api/v1"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/deskbuddy"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080", "http://localhost:5173"]
    
    # Serial (Arduino/ESP32)
    serial_port: str = "COM3"
    serial_baudrate: int = 115200
    serial_timeout: float = 1.0
    
    # Backend API
    backend_url: str = "http://localhost:8000"
    backend_timeout: float = 30.0
    
    # ML Pipeline
    ml_model_path: str = "models/cnn_model.pth"
    
    # Voice Assistant (Nemotron)
    nvidia_api_key: Optional[str] = None
    nemotron_model: str = "nvidia/nemotron-4-340b-instruct"
    nemotron_base_url: str = "https://integrate.api.nvidia.com/v1"
    voice_timeout: float = 60.0
    voice_disable_thinking: bool = True
    voice_max_tokens: int = 256
    voice_history_turns: int = 6

    # Speech-to-text (faster-whisper, local)
    whisper_model: str = "tiny.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "en"
    whisper_beam_size: int = 1
    whisper_vad_filter: bool = True

    # Text-to-speech (edge-tts neural, SAPI fallback)
    tts_voice: str = "en-US-ChristopherNeural"
    tts_speed: float = 1.0

    # Voice upload guard (the ESP32 sends ~160 KB for 5 seconds of PCM16)
    voice_max_upload_bytes: int = 10 * 1024 * 1024

    # Audio
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 1024
    
    # Desktop Tools
    enable_pc_monitoring: bool = True
    enable_music_control: bool = True
    enable_calendar: bool = True
    enable_voice_assistant: bool = True
    enable_desk_mate: bool = True
    
    # DeskBuddy companion / PC activity engine
    enable_companion: bool = True
    companion_poll_interval: float = 1.0
    companion_sleepy_seconds: int = 30
    companion_sleep_seconds: int = 120
    companion_deep_sleep_seconds: int = 300
    companion_device_timeout: float = 15.0
    companion_push_interval: float = 1.0

    # DeskMate Settings
    desk_mate_theme: str = "dark"
    desk_mate_widget_position: str = "top-right"
    desk_mate_widget_opacity: float = 0.95
    desk_mate_notifications_enabled: bool = True
    desk_mate_hotkeys_enabled: bool = True
    desk_mate_start_minimized: bool = False
    desk_mate_auto_start_pomodoro: bool = False
    
    # WebSocket
    ws_heartbeat_interval: int = 30
    
    # Google Calendar (optional)
    google_credentials_path: Optional[str] = None
    google_token_path: Optional[str] = None
    
    # Outlook Calendar (optional)
    outlook_client_id: Optional[str] = None
    outlook_client_secret: Optional[str] = None
    outlook_tenant_id: Optional[str] = None
    
    # ML Pipeline
    ml_epochs: int = 50
    ml_lr: float = 1e-4
    ml_batch_size: int = 64
    
    # Feature Flags
    enable_pc_monitoring: bool = True
    enable_music_control: bool = True
    enable_calendar: bool = True
    enable_voice_assistant: bool = True
    enable_desk_mate: bool = True
    enable_hardware_bridge: bool = True
    enable_voice_assistant: bool = True
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


settings = Settings()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
LOGS_DIR = PROJECT_ROOT / "logs"

for d in [DATA_DIR, MODELS_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)