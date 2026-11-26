"""
Media models for music control (yt-music-companion inspired).
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.types import UUID, JSONB
import uuid
import enum

from app.core.database import Base


class MediaProvider(str, enum.Enum):
    YOUTUBE_MUSIC = "youtube_music"
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"
    LOCAL = "local"
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"


class PlaybackState(str, enum.Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    BUFFERING = "buffering"


class RepeatMode(str, enum.Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


class MediaQueue(Base):
    __tablename__ = "media_queue"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_mode: Mapped[RepeatMode] = mapped_column(
        SQLEnum(RepeatMode), default=RepeatMode.OFF
    )
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    items: Mapped[List["MediaQueueItem"]] = relationship(
        "MediaQueueItem", back_populates="queue", cascade="all, delete-orphan", order_by="MediaQueueItem.position"
    )
    
    def __repr__(self) -> str:
        return f"<MediaQueue {self.name}>"


class MediaQueueItem(Base):
    __tablename__ = "media_queue_items"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("media_queue.id"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Track info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    album: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    album_art_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Provider info
    provider: Mapped[MediaProvider] = mapped_column(SQLEnum(MediaProvider), default=MediaProvider.YOUTUBE_MUSIC)
    provider_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Video ID, Spotify ID, etc.
    provider_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Metadata
    is_playing: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    played_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    queue: Mapped["MediaQueue"] = relationship("MediaQueue", back_populates="items")
    
    def __repr__(self) -> str:
        return f"<MediaQueueItem {self.title} - {self.artist}>"


class MediaSession(Base):
    __tablename__ = "media_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[MediaProvider] = mapped_column(SQLEnum(MediaProvider), nullable=False)
    state: Mapped[PlaybackState] = mapped_column(SQLEnum(PlaybackState), default=PlaybackState.STOPPED)
    
    # Current track
    current_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_queue_items.id"), nullable=True
    )
    progress_ms: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    volume: Mapped[int] = mapped_column(Integer, default=50)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_mode: Mapped[RepeatMode] = mapped_column(SQLEnum(RepeatMode), default=RepeatMode.OFF)
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Queue reference
    queue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_queue.id"), nullable=True
    )
    
    # Metadata
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    current_item: Mapped[Optional["MediaQueueItem"]] = relationship("MediaQueueItem")
    queue: Mapped[Optional["MediaQueue"]] = relationship("MediaQueue")
    
    def __repr__(self) -> str:
        return f"<MediaSession {self.provider.value} {self.state.value}>"


class Lyrics(Base):
    __tablename__ = "lyrics"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    track_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("media_queue_items.id"))
    provider: Mapped[MediaProvider] = mapped_column(SQLEnum(MediaProvider), nullable=False)
    provider_lyrics_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Lyrics content
    lyrics_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced_lyrics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # LRC format
    translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    track: Mapped["MediaQueueItem"] = relationship("MediaQueueItem")
    
    def __repr__(self) -> str:
        return f"<Lyrics for {self.track_id}>"