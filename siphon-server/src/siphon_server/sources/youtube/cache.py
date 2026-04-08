"""
Two caches:
- youtube metadata
- youtube transcripts
"""

from siphon_server.sources.youtube.metadata import YouTubeMetadata
import re
import sqlite3
from pathlib import Path
from xdg_base_dirs import xdg_cache_home
from typing import Any
import json

ID_RE = re.compile(r"^[A-Za-z0-9\-_]{11}$")


class YouTubeMetadataCache:
    """
    Minimal SQLite-backed cache for YouTube video metadata.
    Location: $XDG_CACHE_HOME/youtube/metadata_cache.db
    Schema:   id TEST PRIMARY KEY, metadata fields as columns"

    Validates video_id format and metadata schema on set.
    Should flag if schema drifts.
    """

    def __init__(self):
        cache_root = Path(xdg_cache_home()) / "siphon" / "youtube"
        cache_root.mkdir(parents=True, exist_ok=True)
        self.path = cache_root / "metadata_cache.db"
        self._con = sqlite3.connect(self.path, check_same_thread=False)
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS metadata ("
            "id TEXT PRIMARY KEY, "
            "url TEXT, "
            "domain TEXT, "
            "title TEXT, "
            "published_date TEXT, "
            "video_id TEXT, "
            "channel TEXT, "
            "duration INT, "
            "description TEXT, "
            "tags TEXT) STRICT"
        )
        self._con.commit()

    # Getters and setters
    def get(self, video_id: str) -> dict[str, Any] | None:
        self._validate_id(video_id)
        # Fetch row from database
        row = self._con.execute(
            "SELECT * FROM metadata WHERE id = ?",
            (video_id,),
        ).fetchone()
        if row:
            metadata = self._convert_SQL_to_metadata(row)
            return metadata
        else:
            return None

    def set(self, video_id: str, metadata: dict[str, str | int]) -> None:
        self._validate_id(video_id)
        validated_metadata = YouTubeMetadata.model_validate(metadata, strict=True)
        metadata = validated_metadata.model_dump()
        # Convert metadata to SQL-compatible tuple
        metadata_tuple = self._convert_metadata_to_SQL(metadata)
        self._con.execute(
            "INSERT OR REPLACE INTO metadata ("
            "id, url, domain, title, published_date, video_id, channel, duration, description, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (video_id, *metadata_tuple),
        )
        self._con.commit()

    def wipe(self) -> None:
        self._con.execute("DELETE FROM metadata")
        self._con.commit()

    # Converters
    def _convert_metadata_to_SQL(self, metadata: dict[str, str]) -> tuple:
        """
        Need to convert tags list to string for SQL storage
        """
        validated_metadata = YouTubeMetadata.model_validate(metadata, strict=True)
        metadata = validated_metadata.model_dump()
        tags = metadata.get("tags")
        if isinstance(tags, list):
            tags_str = json.dumps(tags)  # Convert list to JSON string
        elif tags is None:
            tags_str = None
        else:
            tags_str = str(tags)  # Just in case it's something else

        return (
            metadata.get("url"),
            metadata.get("domain"),
            metadata.get("title"),
            metadata.get("published_date"),
            metadata.get("video_id"),
            metadata.get("channel"),
            metadata.get("duration"),
            metadata.get("description"),
            tags_str,
        )

    def _convert_SQL_to_metadata(self, row: tuple) -> dict[str, str]:
        """
        Need to rehydrate tags json string back to list
        """
        (
            _,
            url,
            domain,
            title,
            published_date,
            video_id,
            channel,
            duration,
            description,
            tags_str,
        ) = row

        # Convert tags JSON string back to list
        if tags_str is not None:
            try:
                tags = json.loads(tags_str)
                if not isinstance(tags, list):
                    tags = []
            except json.JSONDecodeError:
                tags = []
        else:
            tags = []

        metadata = {
            "url": url,
            "domain": domain,
            "title": title,
            "published_date": published_date,
            "video_id": video_id,
            "channel": channel,
            "duration": duration,
            "description": description,
            "tags": tags,
        }
        validated_metadata = YouTubeMetadata.model_validate(metadata, strict=True)
        return validated_metadata.model_dump()

    # Validation methods
    @staticmethod
    def _validate_id(video_id: str) -> None:
        if not ID_RE.match(video_id):
            raise ValueError("video_id must be 11 chars of [A-Za-z0-9\-_].")


class YouTubeTranscriptCache:
    """
    Minimal SQLite-backed cache for YouTube transcripts.

    Location: $XDG_CACHE_HOME/youtube/transcript_cache.db
    Schema:   transcripts(id TEXT PRIMARY KEY, transcript TEXT NOT NULL)
    """

    def __init__(self):
        cache_root = Path(xdg_cache_home()) / "siphon" / "youtube"
        cache_root.mkdir(parents=True, exist_ok=True)
        self.path = cache_root / "transcript_cache.db"
        self._con = sqlite3.connect(self.path, check_same_thread=False)
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS transcripts ("
            "id TEXT PRIMARY KEY, "
            "transcript TEXT NOT NULL)"
        )
        self._con.commit()

    def get(self, video_id: str) -> str | None:
        self._validate_id(video_id)
        row = self._con.execute(
            "SELECT transcript FROM transcripts WHERE id = ?",
            (video_id,),
        ).fetchone()
        return row[0] if row else None

    def set(self, video_id: str, transcript: str) -> None:
        self._validate_id(video_id)
        self._con.execute(
            "INSERT OR REPLACE INTO transcripts (id, transcript) VALUES (?, ?)",
            (video_id, transcript),
        )
        self._con.commit()

    def wipe(self) -> None:
        self._con.execute("DELETE FROM transcripts")
        self._con.commit()

    @staticmethod
    def _validate_id(video_id: str) -> None:
        if not ID_RE.match(video_id):
            raise ValueError("video_id must be 11 chars of [A-Za-z0-9].")
