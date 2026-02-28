from __future__ import annotations

from typing import TYPE_CHECKING

from siphon_server.database.postgres.connection import SessionLocal
from siphon_server.database.postgres.converters import from_orm
from siphon_server.database.postgres.models import ProcessedContentORM

if TYPE_CHECKING:
    from siphon_api.enums import SourceType
    from siphon_api.models import ProcessedContent


def semantic_search(
    query_vector: list[float],
    *,
    limit: int = 10,
    source_type: SourceType | None = None,
) -> list[ProcessedContent]:
    """Return the nearest neighbours to query_vector by cosine distance.

    Only rows with a non-NULL embedding are considered.  Results are ordered
    closest-first (lowest cosine distance = most similar).
    """
    db = SessionLocal()
    try:
        q = db.query(ProcessedContentORM).filter(
            ProcessedContentORM.embedding.isnot(None)
        )
        if source_type is not None:
            q = q.filter(ProcessedContentORM.source_type == source_type.value)
        q = q.order_by(
            ProcessedContentORM.embedding.cosine_distance(query_vector)
        ).limit(limit)
        return [from_orm(row) for row in q.all()]
    finally:
        db.close()
