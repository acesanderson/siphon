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
        mode: Literal["sql", "hybrid", "semantic", "fts", "fuzzy"] = "hybrid",
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
        extension: str | None = None,
        use_hyde: bool = True,
    ) -> Collection[ProcessedContent]:
        """
        Search for content using different search strategies.

        Args:
            query: Search query string
            mode: Search mode. "hybrid" (default) fuses BM25 + semantic via RRF.
                "semantic" is vector-only. "fts" is BM25-only. "sql" is the
                legacy ILIKE-over-title-and-description path. "fuzzy" is
                reserved.
            source_type: Optional filter by source type
            date_filter: Date filter applied post-hoc for non-sql modes
            limit: Maximum number of results
            extension: Extension filter applied post-hoc for non-sql modes
            use_hyde: When True (default), generate a HyDE hypothetical
                answer via gpt-oss and embed that. When False, embed the
                raw query. Only affects hybrid and semantic modes.

        Returns:
            Collection of ProcessedContent objects
        """
        if mode in ("hybrid", "semantic"):
            from siphon_client.retrieval import embed_query, hyde_passage

            text_to_embed = hyde_passage(query) if use_hyde else query
            vec = embed_query(text_to_embed)

            if mode == "hybrid":
                ranked = self.repository.search_hybrid(
                    query=query,
                    query_embedding=vec,
                    limit=max(limit * 3, limit),
                    source_type=source_type,
                )
            else:
                ranked = self.repository.search_semantic(
                    embedding=vec,
                    limit=max(limit * 3, limit),
                    source_type=source_type,
                )
            return self._hydrate_uris(
                [uri for uri, _ in ranked],
                date_filter=date_filter,
                extension=extension,
                limit=limit,
            )

        if mode == "fts":
            ranked = self.repository.search_fts(
                query=query,
                limit=max(limit * 3, limit),
                source_type=source_type,
            )
            return self._hydrate_uris(
                [uri for uri, _ in ranked],
                date_filter=date_filter,
                extension=extension,
                limit=limit,
            )

        if mode == "sql":
            results = self.repository.search_by_text(
                query=query,
                source_type=source_type,
                date_filter=date_filter,
                limit=limit,
                extension=extension,
            )
            return Collection(results, self)

        if mode == "fuzzy":
            raise NotImplementedError(
                "Fuzzy search not yet implemented. "
                "Use mode='hybrid' (default), 'semantic', 'fts', or 'sql'."
            )

        raise ValueError(f"Unknown search mode: {mode}")

    def _hydrate_uris(
        self,
        uris: list[str],
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None,
        extension: str | None,
        limit: int,
    ) -> Collection[ProcessedContent]:
        """Fetch ProcessedContent for ranked URIs, post-filter, truncate.

        Preserves the ranking order from the search call. Post-filters by
        date_filter and extension since search_fts / search_semantic /
        search_hybrid don't accept them. Caller requests an over-fetched
        limit so post-filtering doesn't undercount in the typical case.
        """
        from datetime import datetime as _dt

        results: list[ProcessedContent] = []
        for uri in uris:
            pc = self.repository.get(uri)
            if pc is None:
                continue
            if extension:
                ext = extension.lstrip(".").lower()
                if not pc.source.uri.startswith(f"doc:///{ext}/"):
                    continue
            if date_filter:
                op, dt = date_filter
                ts = int(_dt.timestamp(dt))
                created = pc.created_at
                if op == ">" and not created > ts:
                    continue
                if op == "<" and not created < ts:
                    continue
                if op == ">=" and not created >= ts:
                    continue
                if op == "<=" and not created <= ts:
                    continue
            results.append(pc)
            if len(results) >= limit:
                break
        return Collection(results, self)

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
