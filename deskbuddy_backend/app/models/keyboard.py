"""
Keyboard models for deskey-v2 inspired key mapping and macros.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Integer, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.types import UUID, JSONB
import uuid
import enum

from app.core.database import Base


class KeyCode(str, enum.Enum):
    # Standard keys
    A = "KeyA"
    B = "KeyB"
    C = "KeyC"
    D = "KeyD"
    E = "KeyE"
    F = "KeyF"
    G = "KeyG"
    H = "KeyH"
    I = "KeyI"
    J = "KeyJ"
    K = "KeyK"
    L = "KeyL"
    M = "KeyM"
    N = "KeyN"
    O = "KeyO"
    P = "KeyP"
    Q = "KeyQ"
    R = "KeyR"
    S = "KeyS"
    T = "KeyT"
    U = "KeyU"
    V = "KeyV"
    W = "KeyW"
    X = "KeyX"
    Y = "KeyY"
    Z = "KeyZ"
    
    # Numbers
    NUM_0 = "Digit0"
    NUM_1 = "Digit1"
    NUM_2 = "Digit2"
    NUM_3 = "Digit3"
    NUM_4 = "Digit4"
    NUM_5 = "Digit5"
    NUM_6 = "Digit6"
    NUM_7 = "Digit7"
    NUM_8 = "Digit8"
    NUM_9 = "Digit9"
    
    # Function keys
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    F6 = "F6"
    F7 = "F7"
    F8 = "F8"
    F9 = "F9"
    F10 = "F10"
    F11 = "F11"
    F12 = "F12"
    
    # Modifiers
    LEFT_CTRL = "ControlLeft"
    RIGHT_CTRL = "ControlRight"
    LEFT_SHIFT = "ShiftLeft"
    RIGHT_SHIFT = "ShiftRight"
    LEFT_ALT = "AltLeft"
    RIGHT_ALT = "AltRight"
    LEFT_META = "MetaLeft"
    RIGHT_META = "MetaRight"
    
    # Special
    ENTER = "Enter"
    SPACE = "Space"
    TAB = "Tab"
    BACKSPACE = "Backspace"
    DELETE = "Delete"
    ESCAPE = "Escape"
    CAPS_LOCK = "CapsLock"
    
    # Arrow keys
    UP = "ArrowUp"
    DOWN = "ArrowDown"
    LEFT = "ArrowLeft"
    RIGHT = "ArrowRight"
    
    # Media keys
    MEDIA_PLAY_PAUSE = "MediaPlayPause"
    MEDIA_NEXT = "MediaTrackNext"
    MEDIA_PREV = "MediaTrackPrevious"
    MEDIA_STOP = "MediaStop"
    VOLUME_UP = "VolumeUp"
    VOLUME_DOWN = "VolumeDown"
    VOLUME_MUTE = "VolumeMute"
    
    # Numpad
    NUMPAD_0 = "Numpad0"
    NUMPAD_1 = "Numpad1"
    NUMPAD_2 = "Numpad2"
    NUMPAD_3 = "Numpad3"
    NUMPAD_4 = "Numpad4"
    NUMPAD_5 = "Numpad5"
    NUMPAD_6 = "Numpad6"
    NUMPAD_7 = "Numpad7"
    NUMPAD_8 = "Numpad8"
    NUMPAD_9 = "Numpad9"
    NUMPAD_ADD = "NumpadAdd"
    NUMPAD_SUBTRACT = "NumpadSubtract"
    NUMPAD_MULTIPLY = "NumpadMultiply"
    NUMPAD_DIVIDE = "NumpadDivide"
    NUMPAD_ENTER = "NumpadEnter"
    NUMPAD_DECIMAL = "NumpadDecimal"
    
    # Custom
    UNKNOWN = "Unknown"


class ActionType(str, enum.Enum):
    KEY_PRESS = "key_press"
    KEY_RELEASE = "key_release"
    KEY_TAP = "key_tap"  # press + release
    KEY_HOLD = "key_hold"
    KEY_SEQUENCE = "key_sequence"
    MACRO = "macro"
    LAYER_SWITCH = "layer_switch"
    LAYER_MOMENTARY = "layer_momentary"
    LAYER_TOGGLE = "layer_toggle"
    MACRO_RECORD_START = "macro_record_start"
    MACRO_RECORD_STOP = "macro_record_stop"
    MACRO_PLAY = "macro_play"
    MEDIA_CONTROL = "media_control"
    VOLUME = "volume"
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    MOUSE_SCROLL = "mouse_scroll"
    SHELL_COMMAND = "shell_command"
    CUSTOM = "custom"


class KeyboardLayout(Base):
    __tablename__ = "keyboard_layouts"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Layout configuration
    keymap: Mapped[dict] = mapped_column(JSONB, default=dict)  # {layer: {key: action}}
    layers: Mapped[list] = mapped_column(JSONB, default=list)
    default_layer: Mapped[str] = mapped_column(String(50), default="base")
    
    # Hardware
    vendor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Settings
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    macros: Mapped[List["Macro"]] = relationship("Macro", back_populates="layout", cascade="all, delete-orphan")
    key_mappings: Mapped[List["KeyMapping"]] = relationship("KeyMapping", back_populates="layout", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<KeyboardLayout {self.name}>"


class Layer(Base):
    __tablename__ = "layers"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    layout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("keyboard_layouts.id"))
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color
    is_momentary: Mapped[bool] = mapped_column(Boolean, default=False)  # Hold to activate
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = higher priority
    parent_layer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("layers.id"), nullable=True)
    
    # Layer behavior
    is_transparent: Mapped[bool] = mapped_column(Boolean, default=False)  # Pass through to lower layer
    toggle_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Key to toggle this layer
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    layout: Mapped["KeyboardLayout"] = relationship("KeyboardLayout")
    key_mappings: Mapped[List["KeyMapping"]] = relationship("KeyMapping", back_populates="layer", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Layer {self.name}>"


class KeyMapping(Base):
    __tablename__ = "key_mappings"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    layout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("keyboard_layouts.id"))
    layer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("layers.id"), nullable=True)
    
    # Key identification
    key_code: Mapped[str] = mapped_column(String(50), nullable=False)  # KeyCode enum value
    key_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Human readable label
    
    # Modifiers required
    modifiers: Mapped[list] = mapped_column(JSONB, default=list)  # ["ctrl", "shift", "alt", "meta"]
    
    # Action
    action_type: Mapped[ActionType] = mapped_column(SQLEnum(ActionType), nullable=False)
    action_data: Mapped[dict] = mapped_column(JSONB, default=dict)  # Action-specific data
    
    # Conditions
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)  # When this mapping applies
    
    # Priority
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = higher priority
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    layout: Mapped["KeyboardLayout"] = relationship("KeyboardLayout", back_populates="key_mappings")
    layer: Mapped[Optional["Layer"]] = relationship("Layer", back_populates="key_mappings")
    
    def __repr__(self) -> str:
        return f"<KeyMapping {self.key_code} -> {self.action_type.value}>"


class Macro(Base):
    __tablename__ = "macros"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    layout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("keyboard_layouts.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Macro sequence
    steps: Mapped[list] = mapped_column(JSONB, default=list)  # [{action, key, delay, ...}]
    
    # Trigger
    trigger_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Key to trigger macro
    trigger_modifiers: Mapped[list] = mapped_column(JSONB, default=list)
    trigger_type: Mapped[str] = mapped_column(String(20), default="tap")  # tap, hold, double_tap
    
    # Behavior
    repeat: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_interval_ms: Mapped[int] = mapped_column(Integer, default=100)
    max_repeats: Mapped[int] = mapped_column(Integer, default=0)  # 0 = infinite
    
    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    layout: Mapped["KeyboardLayout"] = relationship("KeyboardLayout", back_populates="macros")
    
    def __repr__(self) -> str:
        return f"<Macro {self.name}>"


class KeyEvent(Base):
    __tablename__ = "key_events"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Key info
    key_code: Mapped[str] = mapped_column(String(50), nullable=False)
    key_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Event details
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # press, release, hold, tap
    modifiers: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Context
    active_layer: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    active_layout_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("keyboard_layouts.id"), nullable=True)
    triggered_macro_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("macros.id"), nullable=True)
    triggered_action_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Device info
    device_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    __table_args__ = (
        Index("ix_key_events_timestamp", "timestamp"),
        Index("ix_key_events_layout", "active_layout_id"),
    )
    
    def __repr__(self) -> str:
        return f"<KeyEvent {self.key_code} {self.event_type}>"