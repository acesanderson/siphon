from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from datetime import datetime
from datetime import timedelta
import re

from pydantic import BaseModel
from pydantic import Field

from models import Video
from models import Channel
from models import Playlist
from models import PlaylistItem
from models import SearchResult

if TYPE_CHECKING:
    pass


def parse_iso8601_duration(duration: str) -> timedelta:
    """Parse ISO 8601 duration string (PT1H2M3S) to timedelta.

    Args:
        duration: ISO 8601 duration string

    Returns:
        Parsed timedelta
    """
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, duration)

    if not match:
        return timedelta()

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


class Thumbnail(BaseModel):
    """Thumbnail data from API."""
    url: str
    width: int | None = None
    height: int | None = None


class Thumbnails(BaseModel):
    """Collection of thumbnails."""
    default: Thumbnail | None = None
    medium: Thumbnail | None = None
    high: Thumbnail | None = None
    standard: Thumbnail | None = None
    maxres: Thumbnail | None = None


class VideoSnippet(BaseModel):
    """Video snippet data from API."""
    published_at: str = Field(alias="publishedAt")
    channel_id: str = Field(alias="channelId")
    title: str
    description: str
    thumbnails: Thumbnails
    channel_title: str = Field(alias="channelTitle")
    tags: list[str] = Field(default_factory=list)
    category_id: str | None = Field(default=None, alias="categoryId")
    default_language: str | None = Field(default=None, alias="defaultLanguage")
    default_audio_language: str | None = Field(default=None, alias="defaultAudioLanguage")


class VideoStatistics(BaseModel):
    """Video statistics from API."""
    view_count: str | None = Field(default="0", alias="viewCount")
    like_count: str | None = Field(default="0", alias="likeCount")
    comment_count: str | None = Field(default="0", alias="commentCount")


class VideoContentDetails(BaseModel):
    """Video content details from API."""
    duration: str
    definition: str
    caption: str
    licensed_content: bool = Field(alias="licensedContent")


class VideoResource(BaseModel):
    """Raw video resource from API."""
    id: str
    snippet: VideoSnippet | None = None
    statistics: VideoStatistics | None = None
    content_details: VideoContentDetails | None = Field(default=None, alias="contentDetails")

    def to_video(self) -> Video:
        """Convert raw API resource to clean Video model."""
        snippet = self.snippet or VideoSnippet(
            publishedAt="1970-01-01T00:00:00Z",
            channelId="",
            title="",
            description="",
            thumbnails=Thumbnails(),
            channelTitle=""
        )
        stats = self.statistics or VideoStatistics()
        content = self.content_details

        return Video(
            id=self.id,
            title=snippet.title,
            description=snippet.description,
            channel_id=snippet.channel_id,
            channel_title=snippet.channel_title,
            published_at=datetime.fromisoformat(snippet.published_at.replace('Z', '+00:00')),
            thumbnail_default=snippet.thumbnails.default.url if snippet.thumbnails.default else None,
            thumbnail_medium=snippet.thumbnails.medium.url if snippet.thumbnails.medium else None,
            thumbnail_high=snippet.thumbnails.high.url if snippet.thumbnails.high else None,
            thumbnail_standard=snippet.thumbnails.standard.url if snippet.thumbnails.standard else None,
            thumbnail_maxres=snippet.thumbnails.maxres.url if snippet.thumbnails.maxres else None,
            view_count=int(stats.view_count or 0),
            like_count=int(stats.like_count or 0),
            comment_count=int(stats.comment_count or 0),
            duration=parse_iso8601_duration(content.duration) if content else None,
            definition=content.definition if content else None,
            caption=content.caption == "true" if content else False,
            licensed_content=content.licensed_content if content else False,
            tags=snippet.tags,
            category_id=snippet.category_id,
            default_language=snippet.default_language,
            default_audio_language=snippet.default_audio_language,
        )


class ChannelSnippet(BaseModel):
    """Channel snippet from API."""
    title: str
    description: str
    custom_url: str | None = Field(default=None, alias="customUrl")
    published_at: str = Field(alias="publishedAt")
    thumbnails: Thumbnails
    country: str | None = None


class ChannelStatistics(BaseModel):
    """Channel statistics from API."""
    subscriber_count: str | None = Field(default="0", alias="subscriberCount")
    video_count: str | None = Field(default="0", alias="videoCount")
    view_count: str | None = Field(default="0", alias="viewCount")


class ChannelResource(BaseModel):
    """Raw channel resource from API."""
    id: str
    snippet: ChannelSnippet | None = None
    statistics: ChannelStatistics | None = None

    def to_channel(self) -> Channel:
        """Convert raw API resource to clean Channel model."""
        snippet = self.snippet or ChannelSnippet(
            title="",
            description="",
            publishedAt="1970-01-01T00:00:00Z",
            thumbnails=Thumbnails()
        )
        stats = self.statistics or ChannelStatistics()

        return Channel(
            id=self.id,
            title=snippet.title,
            description=snippet.description,
            custom_url=snippet.custom_url,
            published_at=datetime.fromisoformat(snippet.published_at.replace('Z', '+00:00')),
            thumbnail_default=snippet.thumbnails.default.url if snippet.thumbnails.default else None,
            thumbnail_medium=snippet.thumbnails.medium.url if snippet.thumbnails.medium else None,
            thumbnail_high=snippet.thumbnails.high.url if snippet.thumbnails.high else None,
            subscriber_count=int(stats.subscriber_count or 0),
            video_count=int(stats.video_count or 0),
            view_count=int(stats.view_count or 0),
            country=snippet.country,
        )


class PlaylistSnippet(BaseModel):
    """Playlist snippet from API."""
    published_at: str = Field(alias="publishedAt")
    channel_id: str = Field(alias="channelId")
    title: str
    description: str
    thumbnails: Thumbnails
    channel_title: str = Field(alias="channelTitle")


class PlaylistContentDetails(BaseModel):
    """Playlist content details from API."""
    item_count: int = Field(alias="itemCount")


class PlaylistResource(BaseModel):
    """Raw playlist resource from API."""
    id: str
    snippet: PlaylistSnippet | None = None
    content_details: PlaylistContentDetails | None = Field(default=None, alias="contentDetails")

    def to_playlist(self) -> Playlist:
        """Convert raw API resource to clean Playlist model."""
        snippet = self.snippet or PlaylistSnippet(
            publishedAt="1970-01-01T00:00:00Z",
            channelId="",
            title="",
            description="",
            thumbnails=Thumbnails(),
            channelTitle=""
        )
        content = self.content_details

        return Playlist(
            id=self.id,
            title=snippet.title,
            description=snippet.description,
            channel_id=snippet.channel_id,
            channel_title=snippet.channel_title,
            published_at=datetime.fromisoformat(snippet.published_at.replace('Z', '+00:00')),
            thumbnail_default=snippet.thumbnails.default.url if snippet.thumbnails.default else None,
            thumbnail_medium=snippet.thumbnails.medium.url if snippet.thumbnails.medium else None,
            thumbnail_high=snippet.thumbnails.high.url if snippet.thumbnails.high else None,
            thumbnail_standard=snippet.thumbnails.standard.url if snippet.thumbnails.standard else None,
            thumbnail_maxres=snippet.thumbnails.maxres.url if snippet.thumbnails.maxres else None,
            item_count=content.item_count if content else 0,
        )


class PlaylistItemSnippet(BaseModel):
    """Playlist item snippet from API."""
    published_at: str = Field(alias="publishedAt")
    channel_id: str = Field(alias="channelId")
    title: str
    description: str
    thumbnails: Thumbnails
    channel_title: str = Field(alias="channelTitle")
    playlist_id: str = Field(alias="playlistId")
    position: int
    resource_id: dict[str, Any] = Field(alias="resourceId")


class PlaylistItemResource(BaseModel):
    """Raw playlist item resource from API."""
    id: str
    snippet: PlaylistItemSnippet

    def to_playlist_item(self) -> PlaylistItem:
        """Convert raw API resource to clean PlaylistItem model."""
        video_id = self.snippet.resource_id.get("videoId", "")

        return PlaylistItem(
            id=self.id,
            playlist_id=self.snippet.playlist_id,
            video_id=video_id,
            title=self.snippet.title,
            description=self.snippet.description,
            channel_id=self.snippet.channel_id,
            channel_title=self.snippet.channel_title,
            published_at=datetime.fromisoformat(self.snippet.published_at.replace('Z', '+00:00')),
            position=self.snippet.position,
            thumbnail_default=self.snippet.thumbnails.default.url if self.snippet.thumbnails.default else None,
            thumbnail_medium=self.snippet.thumbnails.medium.url if self.snippet.thumbnails.medium else None,
            thumbnail_high=self.snippet.thumbnails.high.url if self.snippet.thumbnails.high else None,
        )


class SearchResultId(BaseModel):
    """Search result ID from API."""
    kind: str
    video_id: str | None = Field(default=None, alias="videoId")
    channel_id: str | None = Field(default=None, alias="channelId")
    playlist_id: str | None = Field(default=None, alias="playlistId")


class SearchResultSnippet(BaseModel):
    """Search result snippet from API."""
    published_at: str = Field(alias="publishedAt")
    channel_id: str = Field(alias="channelId")
    title: str
    description: str
    thumbnails: Thumbnails
    channel_title: str = Field(alias="channelTitle")


class SearchResultResource(BaseModel):
    """Raw search result from API."""
    id: SearchResultId
    snippet: SearchResultSnippet

    def to_search_result(self) -> SearchResult:
        """Convert raw API resource to clean SearchResult model."""
        kind_map = {
            "youtube#video": "video",
            "youtube#channel": "channel",
            "youtube#playlist": "playlist",
        }
        kind = kind_map.get(self.id.kind, self.id.kind)

        result_id = self.id.video_id or self.id.channel_id or self.id.playlist_id or ""

        return SearchResult(
            id=result_id,
            kind=kind,
            title=self.snippet.title,
            description=self.snippet.description,
            published_at=datetime.fromisoformat(self.snippet.published_at.replace('Z', '+00:00')),
            channel_id=self.snippet.channel_id,
            channel_title=self.snippet.channel_title,
            thumbnail_default=self.snippet.thumbnails.default.url if self.snippet.thumbnails.default else None,
            thumbnail_medium=self.snippet.thumbnails.medium.url if self.snippet.thumbnails.medium else None,
            thumbnail_high=self.snippet.thumbnails.high.url if self.snippet.thumbnails.high else None,
        )


class VideosResponse(BaseModel):
    """Response from videos.list endpoint."""
    items: list[VideoResource]


class ChannelsResponse(BaseModel):
    """Response from channels.list endpoint."""
    items: list[ChannelResource]


class PlaylistsResponse(BaseModel):
    """Response from playlists.list endpoint."""
    items: list[PlaylistResource]


class PlaylistItemsResponse(BaseModel):
    """Response from playlistItems.list endpoint."""
    items: list[PlaylistItemResource]
    next_page_token: str | None = Field(default=None, alias="nextPageToken")
    prev_page_token: str | None = Field(default=None, alias="prevPageToken")


class SearchResponse(BaseModel):
    """Response from search.list endpoint."""
    items: list[SearchResultResource]
    next_page_token: str | None = Field(default=None, alias="nextPageToken")
    prev_page_token: str | None = Field(default=None, alias="prevPageToken")
