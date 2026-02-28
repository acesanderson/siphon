from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from siphon_api.enums import SourceType
from siphon_api.models import ProcessedContent, QueryHistory
from siphon_server.database.postgres.connection import SessionLocal
from siphon_server.database.postgres.models import ProcessedContentORM, QueryHistoryORM
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
