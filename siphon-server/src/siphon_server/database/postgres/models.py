# pyright: basic
# ^^^ because of SQLAlchemy dynamic attributes

from sqlalchemy import Column, Integer, String, Text, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from siphon_server.database.postgres.connection import Base


class ProcessedContentORM(Base):
    __tablename__ = "processed_content"

    # Primary key: integer for internal DB operations
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Natural key: URI for lookups (unique + indexed)
    uri = Column(String, unique=True, nullable=False, index=True)

    # SourceInfo fields
    source_type = Column(String, nullable=False, index=True)
    original_source = Column(String, nullable=False)
    source_hash = Column(String)

    # ContentData
    content_text = Column(Text, nullable=False)
    content_metadata = Column(JSONB, default=dict)

    # EnrichedData fields
    title = Column(String, default="")
    description = Column(Text, default="")
    summary = Column(Text, default="")
    topics = Column(ARRAY(String), default=list)
    entities = Column(ARRAY(String), default=list)

    # ProcessedContent fields
    tags = Column(ARRAY(String), default=list)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)


class QueryHistoryORM(Base):
    """
    Query execution history for CLI recall functionality.

    Stores query parameters and lightweight result metadata to enable
    "arrow-up" style query history navigation via `siphon results`.
    """
    __tablename__ = "query_history"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Query description (for display in --history list)
    query_string = Column(String, default="")
    source_type = Column(String, nullable=True)
    extension = Column(String, nullable=True)

    # Timestamp (indexed for chronological ordering)
    executed_at = Column(Integer, nullable=False, index=True)

    # Results as JSONB
    # Structure: [{"uri": "...", "title": "...", "source_type": "...", "created_at": ...}]
    results = Column(JSONB, nullable=False)
