from __future__ import annotations

from typing import TYPE_CHECKING
import time
import os

import requests

from models import Video
from models import Channel
from models import Playlist
from models import PlaylistItem
from models import SearchResult
from api import VideosResponse
from api import ChannelsResponse
from api import PlaylistsResponse
from api import PlaylistItemsResponse
from api import SearchResponse

API_KEY = os.getenv("YOUTUBE_API_KEY2")

if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY2 environment variable not set")

if TYPE_CHECKING:
    from collections.abc import Sequence


class YouTubeAPIError(Exception):
    """Base exception for YouTube API errors."""

    pass


class YouTubeClient:
    """Read-only client for YouTube Data API v3.

    Features:
    - Clean, typed interface with flattened models
    - Automatic pagination (up to 200 results)
    - Rate limiting (5 req/sec)
    - Exponential backoff retry (3 attempts)
    - Type conversions (ISO durations, timestamps, etc.)
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"
    MAX_RESULTS_CAP = 200
    DEFAULT_N_RESULTS = 10
    RATE_LIMIT_DELAY = 0.2  # 5 requests/second
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds

    def __init__(self, api_key: str, timeout: int = 10):
        """Initialize YouTube client.

        Args:
            api_key: YouTube Data API key
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request with retry logic and error handling.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            YouTubeAPIError: If request fails after retries
        """
        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                self._rate_limit()
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code

                # Extract error message
                error_msg = f"HTTP {status_code}"
                try:
                    error_data = e.response.json()
                    if "error" in error_data:
                        error_msg = (
                            f"{error_msg}: {error_data['error'].get('message', '')}"
                        )
                except Exception:
                    pass

                # Retry on 429 (rate limit) or 5xx (server errors)
                if (
                    status_code in (429, 500, 502, 503, 504)
                    and attempt < self.MAX_RETRIES
                ):
                    delay = self.RETRY_DELAYS[attempt]
                    time.sleep(delay)
                    continue

                raise YouTubeAPIError(error_msg) from e

            except requests.exceptions.RequestException as e:
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[attempt]
                    time.sleep(delay)
                    continue
                raise YouTubeAPIError(f"Request failed: {e}") from e

        raise YouTubeAPIError("Max retries exceeded")

    def get_videos(self, video_ids: str | Sequence[str]) -> list[Video]:
        """Fetch video data by ID(s).

        Args:
            video_ids: Single video ID or list of IDs

        Returns:
            List of Video objects
        """
        if isinstance(video_ids, str):
            video_ids = [video_ids]

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
        }

        data = self._request("videos", params)
        response = VideosResponse(**data)
        return [resource.to_video() for resource in response.items]

    def get_channels(
        self,
        channel_ids: str | Sequence[str] | None = None,
        usernames: str | Sequence[str] | None = None,
    ) -> list[Channel]:
        """Fetch channel data by ID(s) or username(s).

        Args:
            channel_ids: Single channel ID or list of IDs
            usernames: Single username or list of usernames

        Returns:
            List of Channel objects
        """
        params = {
            "part": "snippet,statistics,contentDetails",
        }

        if channel_ids:
            if isinstance(channel_ids, str):
                channel_ids = [channel_ids]
            params["id"] = ",".join(channel_ids)
        elif usernames:
            if isinstance(usernames, str):
                usernames = [usernames]
            params["forUsername"] = ",".join(usernames)
        else:
            raise ValueError("Must provide either channel_ids or usernames")

        data = self._request("channels", params)
        response = ChannelsResponse(**data)
        return [resource.to_channel() for resource in response.items]

    def get_playlists(
        self,
        playlist_ids: str | Sequence[str] | None = None,
        channel_id: str | None = None,
    ) -> list[Playlist]:
        """Fetch playlist data by ID(s) or channel ID.

        Args:
            playlist_ids: Single playlist ID or list of IDs
            channel_id: Get playlists for this channel

        Returns:
            List of Playlist objects
        """
        params = {
            "part": "snippet,contentDetails",
            "maxResults": 50,
        }

        if playlist_ids:
            if isinstance(playlist_ids, str):
                playlist_ids = [playlist_ids]
            params["id"] = ",".join(playlist_ids)
        elif channel_id:
            params["channelId"] = channel_id
        else:
            raise ValueError("Must provide either playlist_ids or channel_id")

        data = self._request("playlists", params)
        response = PlaylistsResponse(**data)
        return [resource.to_playlist() for resource in response.items]

    def get_playlist_items(
        self,
        playlist_id: str,
        n_results: int = DEFAULT_N_RESULTS,
    ) -> list[PlaylistItem]:
        """Fetch items in a playlist with automatic pagination.

        Args:
            playlist_id: Playlist ID
            n_results: Number of results to return (max 200)

        Returns:
            List of PlaylistItem objects
        """
        n_results = min(n_results, self.MAX_RESULTS_CAP)
        items = []
        page_token = None

        while len(items) < n_results:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(50, n_results - len(items)),
            }

            if page_token:
                params["pageToken"] = page_token

            data = self._request("playlistItems", params)
            response = PlaylistItemsResponse(**data)

            items.extend([resource.to_playlist_item() for resource in response.items])

            # Stop if no more pages or we have enough results
            if not response.next_page_token or len(items) >= n_results:
                break

            page_token = response.next_page_token

        return items[:n_results]

    def search(
        self,
        query: str,
        search_type: str | Sequence[str] = "video",
        n_results: int = DEFAULT_N_RESULTS,
        order: str = "relevance",
        **kwargs,
    ) -> list[SearchResult]:
        """Search for videos, channels, or playlists with automatic pagination.

        Args:
            query: Search query
            search_type: Resource type(s): 'video', 'channel', 'playlist'
            n_results: Number of results to return (max 200)
            order: Sort order (relevance, date, rating, title, viewCount)
            **kwargs: Additional API parameters (regionCode, relevanceLanguage, etc.)

        Returns:
            List of SearchResult objects
        """
        if isinstance(search_type, str):
            search_type = [search_type]

        n_results = min(n_results, self.MAX_RESULTS_CAP)
        results = []
        page_token = None

        while len(results) < n_results:
            params = {
                "part": "snippet",
                "q": query,
                "type": ",".join(search_type),
                "maxResults": min(50, n_results - len(results)),
                "order": order,
                **kwargs,
            }

            if page_token:
                params["pageToken"] = page_token

            data = self._request("search", params)
            response = SearchResponse(**data)

            results.extend([resource.to_search_result() for resource in response.items])

            # Stop if no more pages or we have enough results
            if not response.next_page_token or len(results) >= n_results:
                break

            page_token = response.next_page_token

        return results[:n_results]


if __name__ == "__main__":
    client = YouTubeClient(API_KEY)
    # Get a list of playlists for the create @aiDotEngineer (youtube.com/@aiDotEngineer/playlists)
    playlists = client.get_playlists(channel_id="UCXuqSBlHAE6Xw-yeJA0Tunw")
    for playlist in playlists:
        print(f"Playlist: {playlist.title} (ID: {playlist.id})")
        # Get the first 5 items in each playlist
        items = client.get_playlist_items(playlist_id=playlist.id, n_results=5)
        for item in items:
            print(f"  - {item.title} (Video ID: {item.video_id})")
