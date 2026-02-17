from __future__ import annotations

from typing import TYPE_CHECKING
from datetime import datetime
from datetime import timedelta

from pydantic import BaseModel
from pydantic import Field

if TYPE_CHECKING:
    pass


class Video(BaseModel):
    """Human-readable video model with flattened structure."""

    id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: datetime

    # Statistics
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0

    # Content details
    duration: timedelta | None = None
    definition: str | None = None  # 'hd' or 'sd'
    caption: bool = False
    licensed_content: bool = False

    # Additional metadata
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = None
    default_language: str | None = None
    default_audio_language: str | None = None


class Channel(BaseModel):
    """Human-readable channel model with flattened structure."""

    id: str
    title: str
    description: str
    custom_url: str | None = None
    published_at: datetime

    # Statistics
    subscriber_count: int = 0
    video_count: int = 0
    view_count: int = 0

    # Content details
    country: str | None = None


class Playlist(BaseModel):
    """Human-readable playlist model with flattened structure."""

    id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: datetime

    # Content details
    item_count: int = 0


class PlaylistItem(BaseModel):
    """Item within a playlist."""

    id: str
    playlist_id: str
    video_id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: datetime
    position: int


class SearchResult(BaseModel):
    """Search result that can be a video, channel, or playlist."""

    id: str
    kind: str  # 'video', 'channel', or 'playlist'
    title: str
    description: str
    published_at: datetime
    channel_id: str | None = None
    channel_title: str | None = None
