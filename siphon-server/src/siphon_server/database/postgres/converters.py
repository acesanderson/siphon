# pyright: basic

from siphon_api.models import (
    ProcessedContent,
    SourceInfo,
    ContentData,
    EnrichedData,
    QueryHistory,
    QueryResultItem,
)
from siphon_api.enums import SourceType
from siphon_server.database.postgres.models import ProcessedContentORM, QueryHistoryORM


def to_orm(pc: ProcessedContent) -> ProcessedContentORM:
    """Convert domain model to ORM model."""
    return ProcessedContentORM(
        uri=pc.source.uri,
        source_type=pc.source.source_type.value,  # Enum to string
        original_source=pc.source.original_source,
        source_hash=pc.source.hash,
        content_text=pc.content.text,
        content_metadata=pc.content.metadata,
        title=pc.enrichment.title,
        description=pc.enrichment.description,
        summary=pc.enrichment.summary,
        topics=pc.enrichment.topics,
        entities=pc.enrichment.entities,
        tags=pc.tags,
        created_at=pc.created_at,
        updated_at=pc.updated_at,
    )


def from_orm(orm: ProcessedContentORM) -> ProcessedContent:
    """Convert ORM model to domain model."""
    return ProcessedContent(
        source=SourceInfo(
            source_type=SourceType(orm.source_type),  # String to enum
            uri=orm.uri,
            original_source=orm.original_source,
            hash=orm.source_hash,
        ),
        content=ContentData(
            source_type=SourceType(orm.source_type),
            text=orm.content_text,
            metadata=orm.content_metadata or {},
        ),
        enrichment=EnrichedData(
            source_type=SourceType(orm.source_type),
            title=orm.title or "",
            description=orm.description or "",
            summary=orm.summary or "",
            topics=orm.topics or [],
            entities=orm.entities or [],
        ),
        tags=orm.tags or [],
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def query_history_to_orm(qh: QueryHistory) -> QueryHistoryORM:
    """Convert QueryHistory domain model to ORM model."""
    return QueryHistoryORM(
        id=qh.id,
        query_string=qh.query_string,
        source_type=qh.source_type,
        extension=qh.extension,
        executed_at=qh.executed_at,
        results=[item.model_dump() for item in qh.results],  # Pydantic to dict
    )


def query_history_from_orm(orm: QueryHistoryORM) -> QueryHistory:
    """Convert QueryHistoryORM to domain model."""
    return QueryHistory(
        id=orm.id,
        query_string=orm.query_string,
        source_type=orm.source_type,
        extension=orm.extension,
        executed_at=orm.executed_at,
        results=[QueryResultItem(**item) for item in orm.results],  # Dict to Pydantic
    )
