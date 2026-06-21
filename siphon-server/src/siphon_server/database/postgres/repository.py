from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from siphon_api.enums import SourceType
from siphon_api.models import ProcessedContent, QueryHistory
from siphon_server.database.postgres.connection import SessionLocal
from siphon_server.database.postgres.models import (
    EnrichmentRunORM,
    ProcessedContentORM,
    QueryHistoryORM,
)
from siphon_server.database.postgres.converters import (
    to_orm,
    from_orm,
    query_history_to_orm,
    query_history_from_orm,
)
import logging
import json

logger = logging.getLogger(__name__)


class ContentRepository:
    """Self-managing repository with automatic session handling."""

    @contextmanager
    def _session(self):
        """Internal session context manager."""
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, uri: str) -> ProcessedContent | None:
        """Get content by URI. Returns None if not found."""
        with self._session() as db:
            orm_obj = db.query(ProcessedContentORM).filter_by(uri=uri).first()
            return from_orm(orm_obj) if orm_obj else None

    def exists(self, uri: str) -> bool:
        """Check if content exists without loading data."""
        with self._session() as db:
            return db.query(
                db.query(ProcessedContentORM).filter_by(uri=uri).exists()
            ).scalar()

    def set(self, pc: ProcessedContent) -> None:
        """Create or update content."""
        with self._session() as db:
            existing = (
                db.query(ProcessedContentORM).filter_by(uri=pc.source.uri).first()
            )

            if existing:
                # Update
                for key, value in to_orm(pc).__dict__.items():
                    if key not in ("id", "_sa_instance_state"):
                        setattr(existing, key, value)
                db.commit()
                db.refresh(existing)
                logger.info(f"Updated content: {pc.source.uri}")
            else:
                # Create
                orm_obj = to_orm(pc)
                db.add(orm_obj)
                try:
                    db.commit()
                    db.refresh(orm_obj)
                    logger.info(f"Created content: {pc.source.uri}")
                except IntegrityError:
                    db.rollback()
                    raise ValueError(f"Content with URI {pc.source.uri} already exists")

    def create(self, pc: ProcessedContent) -> ProcessedContent:
        """Create new content. Raises ValueError if URI already exists."""
        with self._session() as db:
            orm_obj = to_orm(pc)
            db.add(orm_obj)
            try:
                db.commit()
                db.refresh(orm_obj)
                logger.info(f"Created content: {pc.source.uri}")
                return from_orm(orm_obj)
            except IntegrityError:
                db.rollback()
                raise ValueError(f"Content with URI {pc.source.uri} already exists")

    def update(self, pc: ProcessedContent) -> ProcessedContent:
        """Update existing content. Raises ValueError if not found."""
        with self._session() as db:
            existing = (
                db.query(ProcessedContentORM).filter_by(uri=pc.source.uri).first()
            )
            if not existing:
                raise ValueError(f"Content with URI {pc.source.uri} not found")

            for key, value in to_orm(pc).__dict__.items():
                if key not in ("id", "_sa_instance_state"):
                    setattr(existing, key, value)

            db.commit()
            db.refresh(existing)
            logger.info(f"Updated content: {pc.source.uri}")
            return from_orm(existing)

    def reenrich_row(
        self,
        uri: str,
        title: str,
        description: str,
        summary: str,
        topics: list[str] | None,
        entities: list[str] | None,
        version_tag: str,
    ) -> bool:
        """Replace enriched fields on a single row and NULL the embedding.

        Used by the re-enrichment job (item #2 in evals/STRATEGY.md). NULLing
        the embedding is required because the source artifact for vector
        encoding (the description column under Phase R2) has just changed —
        the old vector no longer corresponds to the new content.

        Idempotency: stamps `_enrichment_version` in content_metadata. Callers
        skip rows where the stamp already matches the current version_tag.

        Returns True if a row was updated, False if no row matched.
        """
        with self._session() as db:
            row = db.query(ProcessedContentORM).filter_by(uri=uri).first()
            if row is None:
                return False
            row.title = title
            row.description = description
            row.summary = summary
            row.topics = list(topics or [])
            row.entities = list(entities or [])
            row.embedding = None
            row.embed_model = None
            meta = dict(row.content_metadata or {})
            meta["_enrichment_version"] = version_tag
            row.content_metadata = meta
            return True

    def list_uris_for_reenrichment(
        self,
        source_type: SourceType | None,
        version_tag: str,
        limit: int | None = None,
    ) -> list[str]:
        """Return URIs whose `_enrichment_version` is not the given tag.

        Filters by source_type if provided. Rows missing the metadata key
        entirely are included — they predate the re-enrichment pass.
        """
        with self._session() as db:
            q = db.query(ProcessedContentORM.uri)
            if source_type is not None:
                q = q.filter(ProcessedContentORM.source_type == source_type.value)
            # JSONB containment: row is "done" iff metadata contains
            # {"_enrichment_version": version_tag}. We want the opposite.
            from sqlalchemy import not_
            q = q.filter(
                not_(
                    ProcessedContentORM.content_metadata.contains(
                        {"_enrichment_version": version_tag}
                    )
                )
            )
            q = q.order_by(ProcessedContentORM.created_at.asc())
            if limit is not None:
                q = q.limit(limit)
            return [row.uri for row in q.all()]

    def get_existing_uris(self, uris: list[str]) -> list[str]:
        """Batch check which URIs exist. Returns list of existing URIs."""
        with self._session() as db:
            results = (
                db.query(ProcessedContentORM.uri)
                .filter(ProcessedContentORM.uri.in_(uris))
                .all()
            )
            return [row.uri for row in results]

    # Archival methods for cli
    def get_last_processed_content(self) -> ProcessedContent | None:
        """Get the last processed content based on creation time."""
        with self._session() as db:
            orm_obj = (
                db.query(ProcessedContentORM)
                .order_by(ProcessedContentORM.created_at.desc())
                .first()
            )
            return from_orm(orm_obj) if orm_obj else None

    def delete(self, uri: str) -> bool:
        """Delete content by URI. Returns True if deleted, False if not found."""
        with self._session() as db:
            deleted = (
                db.query(ProcessedContentORM)
                .filter_by(uri=uri)
                .delete(synchronize_session=False)
            )
            return deleted > 0

    def get_all_uris_by_source_type(self, source_type: SourceType) -> list[str]:
        """Return all URIs for a given source type."""
        with self._session() as db:
            rows = (
                db.query(ProcessedContentORM.uri)
                .filter(ProcessedContentORM.source_type == source_type.value)
                .all()
            )
            return [row.uri for row in rows]

    def get_sync_metadata(
        self, source_type: SourceType
    ) -> dict[str, tuple[int, str | None, int]]:
        """Return {uri: (updated_at, source_hash, content_len)} for all records
        of the given source type. Single query; used by the sync loop to avoid
        N+1 full-row reads.
        """
        with self._session() as db:
            from sqlalchemy import func
            rows = (
                db.query(
                    ProcessedContentORM.uri,
                    ProcessedContentORM.updated_at,
                    ProcessedContentORM.source_hash,
                    func.length(ProcessedContentORM.content_text).label("content_len"),
                )
                .filter(ProcessedContentORM.source_type == source_type.value)
                .all()
            )
            return {
                row.uri: (row.updated_at, row.source_hash, row.content_len)
                for row in rows
            }

    def get_backlinks(self, uri: str) -> list[ProcessedContent]:
        """Find all records whose wikilinks metadata contains the given URI."""
        with self._session() as db:
            results = (
                db.query(ProcessedContentORM)
                .filter(
                    ProcessedContentORM.content_metadata.contains(
                        {"wikilinks": [uri]}
                    )
                )
                .all()
            )
            return [from_orm(r) for r in results]

    # Query methods for siphon query command
    def search_by_text(
        self,
        query: str,
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
        extension: str | None = None,
    ) -> list[ProcessedContent]:
        """
        Search for content by plaintext match in title OR description.

        Performs case-insensitive SQL ILIKE search on title and description fields.
        Returns ProcessedContent objects sorted by created_at descending (newest first).

        Args:
            query: Search text to match against title or description
            source_type: Optional filter by SourceType
            date_filter: Optional tuple of (operator, datetime) for date filtering
            limit: Maximum number of results to return
            extension: Optional filter by file extension (e.g., "pdf", "docx")
                      Only applies to DOC source types with URIs like "doc:///pdf/hash"

        Returns:
            List of ProcessedContent objects matching the search criteria
        """
        with self._session() as db:
            q = db.query(ProcessedContentORM)

            # Text search in title OR description (case-insensitive)
            if query:
                search_pattern = f"%{query}%"
                q = q.filter(
                    or_(
                        ProcessedContentORM.title.ilike(search_pattern),
                        ProcessedContentORM.description.ilike(search_pattern),
                    )
                )

            # Filter by source type
            if source_type:
                q = q.filter(ProcessedContentORM.source_type == source_type)

            # Filter by extension (only for DOC type with doc:/// URIs)
            if extension:
                # Extension is embedded in URI as: doc:///extension/hash
                extension_pattern = f"doc:///{extension}/%"
                q = q.filter(ProcessedContentORM.uri.like(extension_pattern))

            # Filter by date
            if date_filter:
                operator, date_value = date_filter
                timestamp = int(date_value.timestamp())
                match operator:
                    case ">":
                        q = q.filter(ProcessedContentORM.created_at > timestamp)
                    case "<":
                        q = q.filter(ProcessedContentORM.created_at < timestamp)
                    case ">=":
                        q = q.filter(ProcessedContentORM.created_at >= timestamp)
                    case "<=":
                        q = q.filter(ProcessedContentORM.created_at <= timestamp)

            # Sort by created_at descending (newest first)
            q = q.order_by(ProcessedContentORM.created_at.desc())

            # Apply limit
            q = q.limit(limit)

            results = q.all()
            return [from_orm(orm_obj) for orm_obj in results]

    def get_embed_texts(
        self,
        uris: list[str],
        skip_existing: bool = True,
    ) -> dict[str, tuple[str, str]]:
        """Return {uri: (title, summary)} for URIs that need embedding.

        When skip_existing=True (default), only returns rows where embedding IS NULL,
        so the caller encodes only records that actually need a vector.
        Rows with empty title+summary are included — the caller filters those.
        """
        with self._session() as db:
            q = db.query(
                ProcessedContentORM.uri,
                ProcessedContentORM.title,
                ProcessedContentORM.summary,
            ).filter(ProcessedContentORM.uri.in_(uris))
            if skip_existing:
                q = q.filter(ProcessedContentORM.embedding.is_(None))
            rows = q.all()
            return {row.uri: (row.title or "", row.summary or "") for row in rows}

    def get_embed_descriptions(
        self,
        uris: list[str],
        skip_existing: bool = True,
    ) -> dict[str, str]:
        """Return {uri: description} for URIs that need embedding (Phase R2).

        Replaces `get_embed_texts`: the source artifact for vector embedding
        becomes the HyDE-shaped description, generated by the enricher per
        retrieval.md, rather than the (title, summary) concatenation. Headwater's
        embed-batch service must switch to this method once both nomic-embed
        and the new description guidelines are live across enrichers.

        When skip_existing=True (default), only returns rows where embedding
        IS NULL. Rows with empty description are included — the caller filters
        those.
        """
        with self._session() as db:
            q = db.query(
                ProcessedContentORM.uri,
                ProcessedContentORM.description,
            ).filter(ProcessedContentORM.uri.in_(uris))
            if skip_existing:
                q = q.filter(ProcessedContentORM.embedding.is_(None))
            rows = q.all()
            return {row.uri: (row.description or "") for row in rows}

    def search_fts(
        self,
        query: str,
        limit: int = 50,
        source_type: SourceType | None = None,
    ) -> list[tuple[str, float]]:
        """BM25-style lexical search over the generated tsvector column.

        Returns a list of (uri, rank) tuples sorted by descending rank.
        Uses Postgres `ts_rank_cd` over `fts_doc`, with `plainto_tsquery` so
        natural-language queries don't need to be FTS-syntax-aware. Pair with
        `search_semantic` via `search_hybrid` for RRF.
        """
        from sqlalchemy import text

        sql = """
            SELECT
                uri,
                ts_rank_cd(fts_doc, plainto_tsquery('english', :q)) AS rank
            FROM processed_content
            WHERE fts_doc @@ plainto_tsquery('english', :q)
            {source_filter}
            ORDER BY rank DESC
            LIMIT :limit
        """
        source_filter = ""
        params = {"q": query, "limit": limit}
        if source_type is not None:
            source_filter = "AND source_type = :source_type"
            params["source_type"] = source_type.value
        sql = sql.format(source_filter=source_filter)

        with self._session() as db:
            rows = db.execute(text(sql), params).fetchall()
            return [(row.uri, float(row.rank)) for row in rows]

    def search_semantic(
        self,
        embedding: list[float],
        limit: int = 50,
        source_type: SourceType | None = None,
    ) -> list[tuple[str, float]]:
        """Cosine-similarity vector search via the HNSW index.

        Returns a list of (uri, similarity) tuples sorted by descending
        similarity. Caller embeds the query (or HyDE-generated hypothetical)
        and passes the vector. Pair with `search_fts` via `search_hybrid`.
        """
        from sqlalchemy import text

        sql = """
            SELECT
                uri,
                1 - (embedding <=> CAST(:emb AS vector)) AS similarity
            FROM processed_content
            WHERE embedding IS NOT NULL
            {source_filter}
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :limit
        """
        source_filter = ""
        params = {"emb": str(embedding), "limit": limit}
        if source_type is not None:
            source_filter = "AND source_type = :source_type"
            params["source_type"] = source_type.value
        sql = sql.format(source_filter=source_filter)

        with self._session() as db:
            rows = db.execute(text(sql), params).fetchall()
            return [(row.uri, float(row.similarity)) for row in rows]

    @staticmethod
    def rrf_fuse(
        rankings: list[list[tuple[str, float]]],
        k: int = 60,
        limit: int = 50,
    ) -> list[tuple[str, float]]:
        """Reciprocal Rank Fusion over multiple ranked lists.

        score(d) = sum_s 1 / (k + rank_s(d))   (Cormack et al., SIGIR 2009)

        Inputs: a list of rankings, each a list of (uri, score) ordered by
        descending score. The score column is ignored — only ordering matters.
        Returns the top `limit` fused (uri, rrf_score) tuples.
        """
        from collections import defaultdict

        rrf_scores: dict[str, float] = defaultdict(float)
        for ranking in rankings:
            for rank_idx, (uri, _score) in enumerate(ranking):
                rrf_scores[uri] += 1.0 / (k + rank_idx + 1)
        ordered = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return ordered[:limit]

    def search_hybrid(
        self,
        query: str,
        query_embedding: list[float],
        limit: int = 50,
        per_signal_limit: int = 100,
        rrf_k: int = 60,
        source_type: SourceType | None = None,
    ) -> list[tuple[str, float]]:
        """RRF fusion of BM25 + semantic.

        Default query path. Each signal contributes a ranking; RRF combines
        them without requiring score calibration (BM25 ts_rank_cd and cosine
        similarity are not on comparable scales).
        """
        fts_ranking = self.search_fts(query, limit=per_signal_limit, source_type=source_type)
        sem_ranking = self.search_semantic(query_embedding, limit=per_signal_limit, source_type=source_type)
        return self.rrf_fuse([fts_ranking, sem_ranking], k=rrf_k, limit=limit)

    def set_embeddings_batch(
        self,
        pairs: list[tuple[str, list[float]]],
        model: str,
        force: bool = False,
    ) -> int:
        """Store vectors for (uri, vector) pairs. Returns count stored.

        Idempotent by default (force=False): skips URIs that already have an
        embedding.  Pass force=True to overwrite (e.g., after a model change).
        All pairs are written in a single transaction.
        """
        if not pairs:
            return 0
        uri_to_vector = dict(pairs)
        uris = list(uri_to_vector.keys())
        with self._session() as db:
            q = db.query(ProcessedContentORM).filter(
                ProcessedContentORM.uri.in_(uris)
            )
            if not force:
                q = q.filter(ProcessedContentORM.embedding.is_(None))
            rows = q.all()
            for row in rows:
                row.embedding = uri_to_vector[row.uri]
                row.embed_model = model
            return len(rows)

    def list_all(
        self,
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
        extension: str | None = None,
    ) -> list[ProcessedContent]:
        """
        List all content sorted by created_at descending (newest first).

        Args:
            source_type: Optional filter by SourceType
            date_filter: Optional tuple of (operator, datetime) for date filtering
            limit: Maximum number of results to return
            extension: Optional filter by file extension (e.g., "pdf", "docx")
                      Only applies to DOC source types with URIs like "doc:///pdf/hash"

        Returns:
            List of ProcessedContent objects
        """
        with self._session() as db:
            q = db.query(ProcessedContentORM)

            # Filter by source type
            if source_type:
                q = q.filter(ProcessedContentORM.source_type == source_type)

            # Filter by extension (only for DOC type with doc:/// URIs)
            if extension:
                # Extension is embedded in URI as: doc:///extension/hash
                extension_pattern = f"doc:///{extension}/%"
                q = q.filter(ProcessedContentORM.uri.like(extension_pattern))

            # Filter by date
            if date_filter:
                operator, date_value = date_filter
                timestamp = int(date_value.timestamp())
                match operator:
                    case ">":
                        q = q.filter(ProcessedContentORM.created_at > timestamp)
                    case "<":
                        q = q.filter(ProcessedContentORM.created_at < timestamp)
                    case ">=":
                        q = q.filter(ProcessedContentORM.created_at >= timestamp)
                    case "<=":
                        q = q.filter(ProcessedContentORM.created_at <= timestamp)

            # Sort by created_at descending (newest first)
            q = q.order_by(ProcessedContentORM.created_at.desc())

            # Apply limit
            q = q.limit(limit)

            results = q.all()
            return [from_orm(orm_obj) for orm_obj in results]

    def insert_enrichment_run(
        self,
        *,
        uri: str,
        enriched_at: int,
        tier: str,
        strategy: str,
        token_count: int,
        model: str,
        host: str,
        status: str,
        error_message: str | None,
        duration_seconds: float | None,
        guideline_hash: str,
        trace_json: list[dict],
    ) -> int:
        """Append one enrichment_runs row. Returns the inserted row id."""
        with self._session() as db:
            row = EnrichmentRunORM(
                uri=uri,
                enriched_at=enriched_at,
                tier=tier,
                strategy=strategy,
                token_count=token_count,
                model=model,
                host=host,
                status=status,
                error_message=error_message,
                duration_seconds=duration_seconds,
                guideline_hash=guideline_hash,
                trace_json=trace_json,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id

    def get_latest_enrichment_run(self, uri: str) -> dict | None:
        """Fetch the most recent enrichment_runs row for a URI as a dict.

        Returns None if no run exists. Returned as a plain dict so the CLI
        can render or JSON-emit without dragging the ORM type across layers.
        """
        with self._session() as db:
            row = (
                db.query(EnrichmentRunORM)
                .filter_by(uri=uri)
                .order_by(EnrichmentRunORM.enriched_at.desc())
                .first()
            )
            if row is None:
                return None
            return {
                "id": row.id,
                "uri": row.uri,
                "enriched_at": row.enriched_at,
                "tier": row.tier,
                "strategy": row.strategy,
                "token_count": row.token_count,
                "model": row.model,
                "host": row.host,
                "status": row.status,
                "error_message": row.error_message,
                "duration_seconds": row.duration_seconds,
                "guideline_hash": row.guideline_hash,
                "trace_json": row.trace_json,
            }


class QueryHistoryRepository:
    """Repository for managing query history with automatic session handling."""

    @contextmanager
    def _session(self):
        """Internal session context manager."""
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def save(self, query_history: QueryHistory) -> QueryHistory:
        """
        Save a query history record to the database.

        Args:
            query_history: QueryHistory domain model to save

        Returns:
            QueryHistory with assigned ID
        """
        with self._session() as db:
            orm_obj = query_history_to_orm(query_history)
            db.add(orm_obj)
            db.commit()
            db.refresh(orm_obj)
            logger.info(f"Saved query history: id={orm_obj.id}")
            return query_history_from_orm(orm_obj)

    def get_latest(self) -> QueryHistory | None:
        """
        Get the most recently executed query.

        Returns:
            QueryHistory object or None if no queries exist
        """
        with self._session() as db:
            orm_obj = (
                db.query(QueryHistoryORM)
                .order_by(QueryHistoryORM.executed_at.desc())
                .first()
            )
            return query_history_from_orm(orm_obj) if orm_obj else None

    def get_by_id(self, query_id: int) -> QueryHistory | None:
        """
        Get a query history record by ID.

        Args:
            query_id: The query ID to retrieve

        Returns:
            QueryHistory object or None if not found
        """
        with self._session() as db:
            orm_obj = db.query(QueryHistoryORM).filter_by(id=query_id).first()
            return query_history_from_orm(orm_obj) if orm_obj else None

    def list_recent(self, limit: int = 20) -> list[QueryHistory]:
        """
        List recent queries in chronological order (newest first).

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of QueryHistory objects
        """
        with self._session() as db:
            results = (
                db.query(QueryHistoryORM)
                .order_by(QueryHistoryORM.executed_at.desc())
                .limit(limit)
                .all()
            )
            return [query_history_from_orm(orm_obj) for orm_obj in results]


REPOSITORY = ContentRepository()
