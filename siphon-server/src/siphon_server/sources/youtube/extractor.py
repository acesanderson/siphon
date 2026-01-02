from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import SourceInfo, ContentData
from siphon_api.enums import SourceType
from siphon_server.sources.youtube.metadata import YouTubeMetadata
from siphon_server.sources.youtube.get_video_id import get_video_id
from siphon_server.sources.youtube.cache import (
    YouTubeTranscriptCache,
    YouTubeMetadataCache,
)
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
from functools import lru_cache
from typing import override, Any
import os
import logging

logger = logging.getLogger(__name__)
transcript_cache = YouTubeTranscriptCache()
metadata_cache = YouTubeMetadataCache()

WEBSHARE_USERNAME = os.getenv("WEBSHARE_USERNAME")
WEBSHARE_PASS = os.getenv("WEBSHARE_PASS")
if not WEBSHARE_USERNAME or not WEBSHARE_PASS:
    logger.warning(
        "Webshare credentials not set in environment variables. Transcript downloads may fail if rate limits are exceeded."
    )
    raise EnvironmentError("Webshare credentials not set in environment variables.")


class YouTubeExtractor(ExtractorStrategy):
    """
    Extract content from YouTube.
    """

    source_type: SourceType = SourceType.YOUTUBE

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        """
        Extract content from a YouTube video.
        1. Validate the video ID.
        2. Retrieve metadata using yt-dlp.
        3. Download the transcript
        4. Return ContentData object.
        """
        video_id: str = get_video_id(source.original_source)
        logger.info(f"Processing video_id: {video_id}")
        self._validate_video_id(video_id)
        metadata: dict[str, str] = self._retrieve_metadata(video_id)
        transcript: str = self._retrieve_youtube_transcript(video_id)
        logger.info("Creating ContentData object...")
        content_data = ContentData(
            source_type=SourceType.YOUTUBE,
            text=transcript,
            metadata=metadata,
        )
        return content_data

    def _validate_video_id(self, video_id: str):
        """
        Quick validation to ensure the video ID is valid.
        """
        logger.debug("Validating video ID...")

        import re

        if re.match(r"^[a-zA-Z0-9_\-]{11}$", video_id):
            pass
        else:
            raise ValueError("Invalid YouTube Video ID")

    # Metadata retrieval with caching
    def _retrieve_metadata(self, video_id: str) -> dict[str, Any]:
        """
        Main method to retrieve YouTube metadata with caching.
        """
        logger.debug("Retrieving metadata...")
        # Check cache first
        cached = self._get_cached_metadata(video_id)
        if cached:
            return cached
        # Download metadata using yt-dlp
        metadata = self._use_youtube_metadata_api(video_id)
        # Cache the metadata
        self._set_cached_metadata(video_id, metadata)
        return metadata

    def _get_cached_metadata(self, video_id: str) -> dict[str, Any] | None:
        """
        Retrieve cached metadata.
        """
        logger.debug("Checking cache for metadata...")
        cached = metadata_cache.get(video_id)
        if cached:
            logger.debug("Metadata cache hit!")
            return cached
        else:
            logger.debug("Metadata not found in cache.")
            return None

    def _set_cached_metadata(self, video_id: str, metadata: dict[str, Any]) -> None:
        """
        Cache the metadata.
        """
        logger.debug("Caching metadata...")
        metadata_cache.set(video_id, metadata)

    @lru_cache(maxsize=128)
    def _use_youtube_metadata_api(self, video_id: str) -> dict[str, Any]:
        """
        If not cached, download the metadata using yt-dlp.
        """
        logger.debug("Getting metadata from yt_dlp api...")

        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(video_id, download=False)
            metadata = {
                # Online metadata (standard fields)
                "url": info.get("webpage_url"),
                "domain": "youtube.com",
                "title": info.get("title"),
                "published_date": info.get("upload_date")
                if info.get("upload_date")
                else None,
                # Youtube-specific
                "video_id": info.get("id"),
                "channel": info.get("channel"),
                "duration": info.get("duration"),
                "description": info.get("description"),
                "tags": info.get("tags"),
            }
        # Verify metadata
        validated_metadata = YouTubeMetadata.model_validate(metadata, strict=True)
        return validated_metadata.model_dump()

    # Transcript retrieval with caching
    def _get_cached_transcript(self, video_id: str) -> str | None:
        """
        Check the cache for the transcript.
        """
        logger.debug("Checking cache for transcript...")
        cached = transcript_cache.get(video_id)
        if cached:
            logger.debug("Transcript cache hit!")
            return cached
        else:
            logger.debug("Transcript not found in cache.")
            return None

    def _set_cached_transcript(self, video_id: str, transcript: str) -> None:
        """
        Cache the transcript.
        """
        logger.debug("Caching transcript...")
        transcript_cache.set(video_id, transcript)

    @lru_cache(maxsize=128)
    def _use_youtube_transcript_api(self, video_id: str) -> str:
        """
        If not cached, download the transcript using youtube-transcript-api.
        """
        logger.debug("Using youtube-transcript-api to download transcript...")
        logger.debug("Setting up YouTubeTranscriptApi with Webshare proxy...")
        ytt_api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=WEBSHARE_USERNAME,
                proxy_password=WEBSHARE_PASS,
            )
        )

        # all requests done by ytt_api will now be proxied through Webshare
        logger.debug("Fetching transcript...")
        fetched_transcript = ytt_api.fetch(video_id)
        t = fetched_transcript.to_raw_data()
        assert isinstance(t, list), "Transcript should be a list"
        script = " ".join([line["text"] for line in t])
        assert len(script) > 0, "Transcript should not be empty"
        return script

    def _retrieve_youtube_transcript(self, video_id: str) -> str:
        """
        Main method to retrieve YouTube transcript with caching.
        """
        logger.debug("Downloading transcript...")
        # Check cache first
        cached = self._get_cached_transcript(video_id)
        if cached:
            return cached
        # Download transcript using youtube-transcript-api
        transcript = self._use_youtube_transcript_api(video_id)
        # Cache the transcript
        self._set_cached_transcript(video_id, transcript)
        return transcript
