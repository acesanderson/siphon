"""Destructive migration: swap the embedding column dimension and re-index.

DO NOT RUN without explicit approval. This NULLs every embedding, drops the
HNSW index, alters the column type, and recreates the index. After this runs:

1. The `embedding` column is `vector(768)` for nomic-embed-text-v1.5.
2. Every row's embedding is NULL — must be re-populated by embed-batch.
3. `models.py:EMBED_DIM` must be bumped to 768 before any code reads/writes.

Order of operations end-to-end (this script is step 3):

    1. Land HyDE description rollout (DONE — siphon commits 83fbb23, 11cbab6).
    2. Re-enrich every stored row so it has a description shaped under the new
       guidelines (this is item #2 — separate job, not this script).
    3. Run this script (drops/recreates index, NULLs embeddings).
    4. Bump models.py:EMBED_DIM to 768 and deploy.
    5. Update headwater's embed_batch_siphon_service to use the new model and
       `get_embed_descriptions` (item #1b — separate change).
    6. Re-embed via embed-batch with force=True over all URIs.

Reversing this requires either restoring from a Postgres backup or accepting
re-embedding under the old model. Take a snapshot before running.

Usage:
    uv run python -m siphon_server.database.postgres.migrate_embedding_dim
        --new-dim 768 --dry-run
    uv run python -m siphon_server.database.postgres.migrate_embedding_dim
        --new-dim 768 --confirm 'YES I HAVE A BACKUP'
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import text

from siphon_server.database.postgres.connection import engine

logger = logging.getLogger(__name__)


def _statements(new_dim: int) -> list[str]:
    return [
        # 1. Drop the HNSW index — pgvector cannot ALTER a column under it.
        "DROP INDEX IF EXISTS ix_pc_embedding_hnsw",
        # 2. NULL every embedding. Required before changing the dimension
        #    because pgvector validates row contents against the column type.
        "UPDATE processed_content SET embedding = NULL, embed_model = NULL",
        # 3. Change the column type. Postgres accepts the cast trivially since
        #    all values are NULL.
        f"ALTER TABLE processed_content "
        f"ALTER COLUMN embedding TYPE vector({new_dim})",
        # 4. Recreate the HNSW index at the new dimension.
        "CREATE INDEX IF NOT EXISTS ix_pc_embedding_hnsw "
        "ON processed_content USING hnsw (embedding vector_cosine_ops)",
    ]


def migrate(new_dim: int, dry_run: bool) -> None:
    statements = _statements(new_dim)

    if dry_run:
        logger.info("DRY RUN — would execute %d statements:", len(statements))
        for s in statements:
            logger.info("  %s", s)
        return

    logger.info("Running %d statements against %s", len(statements), engine.url.database)
    with engine.begin() as conn:
        # Pre-flight: count rows that have an embedding so the operator can
        # sanity-check the "stuff we're about to NULL" magnitude.
        count = conn.execute(
            text("SELECT count(*) FROM processed_content WHERE embedding IS NOT NULL")
        ).scalar_one()
        logger.warning("About to NULL %s populated embeddings.", count)

        for s in statements:
            logger.info("EXEC: %s", s)
            conn.execute(text(s))

    logger.info("Migration complete. Next: bump EMBED_DIM in models.py, deploy, then re-embed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-dim", type=int, required=True,
        help="Target embedding dimension. nomic-embed-text-v1.5 is 768.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print SQL but do not execute.",
    )
    parser.add_argument(
        "--confirm", type=str, default="",
        help="Required for non-dry-run execution. Pass exactly 'YES I HAVE A BACKUP'.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.dry_run and args.confirm != "YES I HAVE A BACKUP":
        logger.error(
            "Refusing to run a destructive migration without --confirm "
            "'YES I HAVE A BACKUP'. Take a Postgres snapshot first."
        )
        sys.exit(2)

    migrate(args.new_dim, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
