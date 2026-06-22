"""Phase D embed-batch driver — direct path to backwater.

Bypasses the headwater `/siphon/embed-batch` endpoint (which previously
routed to deepwater under the now-removed `siphon` route key). Instead,
this script chunks URIs siphon-side and POSTs each chunk to
`/conduit/embeddings` on the headwater router, which routes to backwater
(botvinnik) per the `embeddings` route key.

Net effect: embedding compute happens on the dedicated embeddings host
regardless of where the orchestration script runs.

Idempotent by default: skips URIs whose `embedding` column is non-NULL.
Pass --force to re-embed (e.g., after a model change or a guideline
revision that regenerated descriptions).

Usage:
    # Plan only, count what would be embedded
    uv run python scripts/embed_batch_v2.py --dry-run
    # Smoke against 10 URIs
    uv run python scripts/embed_batch_v2.py --limit 10
    # Full corpus
    uv run python scripts/embed_batch_v2.py
    # Re-embed everything regardless of existing vectors
    uv run python scripts/embed_batch_v2.py --force
"""
from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy import text

from headwater_api.classes import ChromaBatch, EmbeddingsRequest
from headwater_api.classes.siphon_classes.requests import SIPHON_EMBED_MODEL_V2
from headwater_client.client.headwater_client import HeadwaterClient
from siphon_server.database.postgres.connection import engine
from siphon_server.database.postgres.repository import ContentRepository

logger = logging.getLogger(__name__)

# HTTP-payload chunk size. Picked for network efficiency, NOT GPU memory.
# Backwater's per-model handler caps the actual GPU batch size internally
# (see headwater-server/docs/backwater_limits.md). Callers do not need to
# know about the embeddings host's VRAM envelope.
_CHUNK_SIZE = 128


def list_uris_to_embed(
    *, force: bool, source_type: str | None, limit: int | None
) -> list[str]:
    sql = (
        "SELECT uri FROM processed_content "
        "WHERE description IS NOT NULL AND length(description) > 0"
    )
    params: dict[str, object] = {}
    if not force:
        sql += " AND embedding IS NULL"
    if source_type is not None:
        sql += " AND source_type = :source_type"
        params["source_type"] = source_type
    sql += " ORDER BY created_at ASC"
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [r[0] for r in rows]


def embed_batch(
    uris: list[str], *, force: bool, model: str, host_alias: str = "headwater"
) -> tuple[int, int]:
    """Chunk and embed. Returns (embedded_count, skipped_count).

    host_alias selects which headwater host receives the embeddings POST.
    Default "headwater" lets the router pick (per routes.yaml). Override to
    "deepwater" / "backwater" / "bywater" to bypass routing.
    """
    repo = ContentRepository()
    descriptions = repo.get_embed_descriptions(uris, skip_existing=not force)
    items = [(uri, descriptions[uri]) for uri in uris if uri in descriptions and descriptions[uri]]
    if not items:
        return 0, len(uris)

    client = HeadwaterClient(host_alias=host_alias)
    embedded_total = 0
    n_chunks = (len(items) + _CHUNK_SIZE - 1) // _CHUNK_SIZE

    for chunk_idx, start in enumerate(range(0, len(items), _CHUNK_SIZE), start=1):
        chunk = items[start:start + _CHUNK_SIZE]
        chunk_uris = [u for u, _ in chunk]
        chunk_texts = [t for _, t in chunk]

        t0 = time.time()
        resp = client.embeddings.generate_embeddings(
            EmbeddingsRequest(
                model=model,
                batch=ChromaBatch(ids=chunk_uris, documents=chunk_texts),
            )
        )
        wall_embed = time.time() - t0
        if len(resp.embeddings) != len(chunk_uris):
            raise RuntimeError(
                f"embeddings count mismatch: got {len(resp.embeddings)} for "
                f"{len(chunk_uris)} URIs in chunk {chunk_idx}"
            )

        stored = repo.set_embeddings_batch(
            list(zip(chunk_uris, resp.embeddings)),
            model=model,
            force=force,
        )
        embedded_total += stored
        logger.info(
            "chunk %d/%d: requested=%d stored=%d embed_wall=%.2fs",
            chunk_idx, n_chunks, len(chunk), stored, wall_embed,
        )

    skipped = len(uris) - embedded_total
    return embedded_total, skipped


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, help="Cap rows processed.")
    p.add_argument("--source-type", help="Filter by SourceType value (e.g. YouTube, Article).")
    p.add_argument("--force", action="store_true", help="Re-embed even if vector exists.")
    p.add_argument("--model", default=SIPHON_EMBED_MODEL_V2, help="Embedding model to use.")
    p.add_argument(
        "--host",
        default="headwater",
        choices=["headwater", "bywater", "backwater", "deepwater", "stillwater"],
        help="Which headwater host to POST to. Default goes through the router.",
    )
    p.add_argument("--dry-run", action="store_true", help="Count matching URIs and exit.")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    uris = list_uris_to_embed(
        force=args.force, source_type=args.source_type, limit=args.limit
    )
    logger.info(
        "Matched %d URIs (force=%s source_type=%s limit=%s)",
        len(uris), args.force, args.source_type, args.limit,
    )
    if args.dry_run:
        return

    embedded, skipped = embed_batch(
        uris, force=args.force, model=args.model, host_alias=args.host
    )
    logger.info("DONE embedded=%d skipped=%d total=%d", embedded, skipped, len(uris))


if __name__ == "__main__":
    main()
