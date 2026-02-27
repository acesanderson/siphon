"""
SiphonClient for querying and retrieving ingested content.

Provides a high-level interface for searching, filtering, and accessing
ProcessedContent objects from the Siphon database.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from siphon_api.enums import SourceType
from siphon_api.models import ProcessedContent
from siphon_client.collections.collection import Collection
from siphon_server.database.postgres.repository import ContentRepository


class SiphonClient:
    """
    Client for querying Siphon's ingested content.

    Provides methods for searching, filtering, and retrieving ProcessedContent
    objects. Returns Collection objects for functional chaining.
    """

    def __init__(self) -> None:
        """Initialize the SiphonClient with a database repository."""
        self.repository = ContentRepository()

    def search(
        self,
        query: str,
        mode: Literal["sql", "semantic", "fuzzy"] = "sql",
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
        extension: str | None = None,
    ) -> Collection[ProcessedContent]:
        """
        Search for content using different search strategies.

        Args:
            query: Search query string
            mode: Search mode - "sql" (default), "semantic", or "fuzzy"
            source_type: Optional filter by source type
            date_filter: Optional tuple of (operator, datetime) for date filtering
            limit: Maximum number of results
            extension: Optional filter by file extension (e.g., "pdf", "docx")

        Returns:
            Collection of ProcessedContent objects

        Raises:
            NotImplementedError: For semantic and fuzzy search modes
        """
        match mode:
            case "sql":
                results = self.repository.search_by_text(
                    query=query,
                    source_type=source_type,
                    date_filter=date_filter,
                    limit=limit,
                    extension=extension,
                )
                return Collection(results, self)

            case "semantic":
                raise NotImplementedError(
                    "Semantic search requires embeddings infrastructure. "
                    "Use mode='sql' for plaintext search."
                )

            case "fuzzy":
                raise NotImplementedError(
                    "Fuzzy search not yet implemented. "
                    "Use mode='sql' for plaintext search."
                )

    def list_all(
        self,
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
        extension: str | None = None,
    ) -> Collection[ProcessedContent]:
        """
        List all content sorted by creation date (newest first).

        Args:
            source_type: Optional filter by source type
            date_filter: Optional tuple of (operator, datetime) for date filtering
            limit: Maximum number of results
            extension: Optional filter by file extension (e.g., "pdf", "docx")

        Returns:
            Collection of ProcessedContent objects
        """
        results = self.repository.list_all(
            source_type=source_type,
            date_filter=date_filter,
            limit=limit,
            extension=extension,
        )
        return Collection(results, self)

    def get_latest(self) -> ProcessedContent | None:
        """
        Get the most recently created content item.

        Returns:
            The latest ProcessedContent, or None if no content exists
        """
        return self.repository.get_last_processed_content()

    def get_by_uri(self, uri: str) -> ProcessedContent | None:
        """
        Get content by its URI.

        Args:
            uri: The content URI (e.g., "doc:///pdf/hash123")

        Returns:
            ProcessedContent if found, None otherwise
        """
        return self.repository.get(uri)

    def traverse(
        self,
        uri: str,
        depth: int = 1,
        backlinks: bool = False,
    ) -> Collection[ProcessedContent]:
        """
        Traverse the wikilink graph from a given URI.

        Args:
            uri: Starting URI (e.g. "obsidian:///My Note")
            depth: How many hops to follow (default 1 = root + direct neighbors)
            backlinks: If True, find all nodes that link TO uri instead

        Returns:
            Collection of reachable ProcessedContent objects.
            Broken links (URI not in DB) are silently skipped.
        """
        if backlinks:
            results = self.repository.get_backlinks(uri)
            return Collection(results, self)

        visited: set[str] = set()
        current_level = [uri]
        all_results: list[ProcessedContent] = []

        for _ in range(depth + 1):
            if not current_level:
                break
            next_level: list[str] = []
            for u in current_level:
                if u in visited:
                    continue
                visited.add(u)
                node = self.repository.get(u)
                if node is None:
                    continue  # broken link — skip gracefully
                all_results.append(node)
                for linked_uri in node.content.metadata.get("wikilinks", []):
                    if linked_uri not in visited:
                        next_level.append(linked_uri)
            current_level = next_level

        return Collection(all_results, self)

    def find_related(
        self,
        uris: list[str],
        query: str,
    ) -> list[ProcessedContent]:
        """
        Find content related to given URIs using semantic search.

        Args:
            uris: List of content URIs to find related items for
            query: Query string to guide the search

        Returns:
            List of related ProcessedContent objects

        Raises:
            NotImplementedError: Semantic search not yet implemented
        """
        raise NotImplementedError(
            "Semantic search requires embeddings infrastructure. "
            "This method will be implemented when vector search is added."
        )
