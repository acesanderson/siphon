# pyright: basic
# ^^^ because of SQLAlchemy dynamic attributes

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, Integer, String, Text, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from siphon_server.database.postgres.connection import Base

# Embedding dimension for sentence-transformers/all-MiniLM-L6-v2.
# Changing this requires a migration + full re-embed of all records.
EMBED_DIM = 384


class ProcessedContentORM(Base):
    __tablename__ = "processed_content"
    __table_args__ = (
        # GIN index enables fast containment queries on wikilinks and other metadata
        Index("ix_pc_metadata_gin", "content_metadata", postgresql_using="gin"),
        # HNSW index for cosine-distance semantic search via pgvector
        Index(
            "ix_pc_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

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

    # Embedding — NULL until embed-batch runs; reset to NULL on every content update
    embedding = Column(Vector(EMBED_DIM), nullable=True)
    embed_model = Column(String, nullable=True)


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
