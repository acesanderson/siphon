"""
One cache, for trafilatura article fetch results.
"""

import sqlite3
from pathlib import Path
from xdg_base_dirs import xdg_cache_home
from siphon_api.enums import SourceType
from siphon_api.models import ContentData
from siphon_api.errors import ArticleCacheError
import json


class ArticleCache:
    """
    Minimal SQLite-backed cache for Article extraction.
    We take url (str) as key, return ContentData object as value.

        kind: Literal["ContentData"] = "ContentData"  # Discriminator
        source_type: SourceType
        text: str  # The actual content (transcript, article text, file contents)
        metadata: dict[str, Any] = Field(default_factory=dict)

    Location: $XDG_CACHE_HOME/siphon/readabilipy/fetch_cache.db
    Schema:   url TEXT PRIMARY KEY, source_type TEXT NOT NULL, text TEXT NOT NULL, metadata TEXT NOT NULL
    """

    def __init__(self):
        cache_root = Path(xdg_cache_home()) / "siphon" / "readabilipy"
        cache_root.mkdir(parents=True, exist_ok=True)
        self.path = cache_root / "fetch.db"
        self._con = sqlite3.connect(self.path, check_same_thread=False)
        try:
            _ = self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS fetch (
                    url TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
        except sqlite3.Error as e:
            raise ArticleCacheError(f"Failed to initialize cache database: {e}")

    # Getters and setters
    def get(self, url: str) -> ContentData | None:
        # Fetch row from database
        try:
            row = self._con.execute(
                "SELECT * FROM fetch WHERE url = ?",
                (url,),
            ).fetchone()
        except sqlite3.Error as e:
            raise ArticleCacheError(f"Failed to fetch from cache database: {e}")
        if row:
            _, source_type, text, metadata_json = row
            metadata = json.loads(metadata_json)
            return ContentData(
                source_type=SourceType(source_type),
                text=text,
                metadata=metadata,
            )

    def set(self, url: str, content_data: ContentData) -> None:
        # Store ContentData object in database
        metadata_json = json.dumps(content_data.metadata)

        try:
            self._con.execute(
                "REPLACE INTO fetch (url, source_type, text, metadata) VALUES (?, ?, ?, ?)",
                (
                    url,
                    content_data.source_type.value,
                    content_data.text,
                    metadata_json,
                ),
            )
            self._con.commit()
        except sqlite3.Error as e:
            raise ArticleCacheError(f"Failed to store in cache database: {e}")

    def wipe(self) -> None:
        self._con.execute("DELETE FROM fetch")
        self._con.commit()
