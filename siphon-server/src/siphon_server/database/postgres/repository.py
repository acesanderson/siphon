from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from siphon_api.enums import SourceType
from siphon_api.models import ProcessedContent
from siphon_server.database.postgres.connection import SessionLocal
from siphon_server.database.postgres.models import ProcessedContentORM
from siphon_server.database.postgres.converters import to_orm, from_orm
import logging

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

    # Query methods for siphon query command
    def search_by_text(
        self,
        query: str,
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
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

    def list_all(
        self,
        source_type: SourceType | None = None,
        date_filter: tuple[Literal[">", "<", ">=", "<="], datetime] | None = None,
        limit: int = 10,
    ) -> list[ProcessedContent]:
        """
        List all content sorted by created_at descending (newest first).

        Args:
            source_type: Optional filter by SourceType
            date_filter: Optional tuple of (operator, datetime) for date filtering
            limit: Maximum number of results to return

        Returns:
            List of ProcessedContent objects
        """
        with self._session() as db:
            q = db.query(ProcessedContentORM)

            # Filter by source type
            if source_type:
                q = q.filter(ProcessedContentORM.source_type == source_type)

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
