"""
Configuration management for Desktop Bridge.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Bridge settings
    bridge_host: str = "0.0.0.0"
    bridge_port: int = 8080
    bridge_debug: bool = True
    
    # Arduino/ESP32 Serial Connection
    serial_port: str = "COM3"  # Windows default, change as needed
    serial_baudrate: int = 115200
    serial_timeout: float = 1.0
    
    # Backend API
    backend_url: str = "http://localhost:8000"
    backend_timeout: float = 30.0
    
    # ML Pipeline
    ml_model_path: str = "ml/signal_fault_classification_pipeline/signal-fault-classification/models/cnn_model.pth"
    
    # Nemotron Voice Assistant
    nvidia_api_key: Optional[str] = None
    nemotron_model: str = "nvidia/nemotron-4-340b-instruct"
    nemotron_base_url: str = "https://integrate.api.nvidia.com/v1"
    
    # Audio (for future voice features)
    audio_sample_rate: int = 16000
    audio_chunk_size: int = 1024
    
    # Desktop Tools
    enable_pc_monitoring: bool = True
    enable_music_control: bool = True
    enable_calendar: bool = True
    enable_voice_assistant: bool = True
    enable_desk_mate: bool = True
    
    # DeskMate Settings
    desk_mate_theme: str = "dark"  # dark, light, auto
    desk_mate_widget_position: str = "top-right"  # top-left, top-right, bottom-left, bottom-right, center
    desk_mate_widget_opacity: float = 0.95
    desk_mate_notifications_enabled: bool = True
    desk_mate_hotkeys_enabled: bool = True
    desk_mate_start_minimized: bool = False
    desk_mate_auto_start_pomodoro: bool = False
    
    # WebSocket
    ws_heartbeat_interval: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure directories exist
for d in [DATA_DIR, MODELS_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)