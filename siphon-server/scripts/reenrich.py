"""Re-enrich stored Siphon rows under the v2 HyDE-shaped pipeline.

Background:

- Before 2026-06-04, descriptions were a human-readable paragraph generated
  in parallel with the summary against raw text.
- After commit 11cbab6, descriptions are HyDE-shaped retrieval artifacts
  generated as a one-shot pass on top of the summary.

This script walks every row in `processed_content`, reconstructs a
`ContentData` from stored fields, re-runs the matching enricher, and writes
the new `title / description / summary / topics / entities` back. It NULLs
the embedding so the v2 embed-batch (item #1b) re-encodes against the new
description.

Idempotent: marks `content_metadata._enrichment_version = <tag>` and skips
rows that already match the tag on subsequent runs.

DO NOT RUN without explicit approval. Re-enrichment fires three LLM calls
per row (summary, description, title) — for a corpus of a few thousand rows
this is hours of inference and a meaningful Headwater bill.

Usage:
    # plan only
    uv run python scripts/reenrich.py --tag hyde_2026_06 --dry-run
    # 5-row smoke
    uv run python scripts/reenrich.py --tag hyde_2026_06 \\
        --source obsidian --limit 5 --confirm 'YES PROCEED'
    # full run for one source
    uv run python scripts/reenrich.py --tag hyde_2026_06 \\
        --source article --confirm 'YES PROCEED'
    # full run across all sources
    uv run python scripts/reenrich.py --tag hyde_2026_06 \\
        --confirm 'YES PROCEED'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from siphon_api.enums import SourceType
from siphon_api.interfaces import EnricherStrategy
from siphon_api.models import ContentData, EnrichedData
from siphon_server.core.enrichment_trace import capture_enrichment
from siphon_server.database.postgres.repository import ContentRepository

logger = logging.getLogger(__name__)
STATUS_PATH = Path(__file__).parent / "reenrich_status.json"

_shutdown = False


def _enricher_for(source_type: SourceType) -> EnricherStrategy:
    """Late-imported enricher dispatch. Lazy because importing all enrichers
    pulls in heavy conduit + headwater modules; we only want the ones we use.
    """
    from siphon_server.sources.article.enricher import ArticleEnricher
    from siphon_server.sources.arxiv.enricher import ArxivEnricher
    from siphon_server.sources.audio.enricher import AudioEnricher
    from siphon_server.sources.doc.enricher import DocEnricher
    from siphon_server.sources.email.enricher import EmailEnricher
    from siphon_server.sources.github.enricher import GitHubEnricher
    from siphon_server.sources.image.enricher import ImageEnricher
    from siphon_server.sources.obsidian.enricher import ObsidianEnricher
    from siphon_server.sources.video.enricher import VideoEnricher
    from siphon_server.sources.youtube.enricher import YouTubeEnricher

    mapping: dict[SourceType, type[EnricherStrategy]] = {
        SourceType.ARTICLE: ArticleEnricher,
        SourceType.ARXIV: ArxivEnricher,
        SourceType.AUDIO: AudioEnricher,
        SourceType.DOC: DocEnricher,
        SourceType.EMAIL: EmailEnricher,
        SourceType.GITHUB: GitHubEnricher,
        SourceType.IMAGE: ImageEnricher,
        SourceType.OBSIDIAN: ObsidianEnricher,
        SourceType.VIDEO: VideoEnricher,
        SourceType.YOUTUBE: YouTubeEnricher,
    }
    cls = mapping.get(source_type)
    if cls is None:
        raise ValueError(
            f"No enricher for source_type={source_type}. drive/podcasts have "
            f"no enricher.py; skip those source types upstream."
        )
    return cls()


def _handle_sigterm(signum, frame) -> None:
    global _shutdown
    _shutdown = True
    logger.info("SIGTERM received — will stop after current row")


def _write_status(payload: dict) -> None:
    STATUS_PATH.write_text(json.dumps(payload, indent=2, default=str))


def _report_progress(progress: float, memo: str) -> None:
    """Cronicle-friendly progress emission. Raw print, not via logger."""
    print(json.dumps({"progress": min(max(progress, 0.0), 1.0), "memo": memo}), flush=True)


async def _reenrich_one(
    uri: str,
    repo: ContentRepository,
    version_tag: str,
    sem: asyncio.Semaphore,
) -> tuple[str, bool, str | None]:
    """Re-enrich one URI. Returns (uri, success, error_message)."""
    async with sem:
        if _shutdown:
            return uri, False, "shutdown"
        pc = repo.get(uri)
        if pc is None:
            return uri, False, "uri vanished between list and fetch"
        try:
            enricher = _enricher_for(pc.source.source_type)
            content = ContentData(
                source_type=pc.source.source_type,
                text=pc.content.text,
                metadata=pc.content.metadata,
            )
            t0 = time.monotonic()
            async with capture_enrichment(uri=uri):
                enriched: EnrichedData = await enricher.enrich(content)
            elapsed = time.monotonic() - t0
            updated = repo.reenrich_row(
                uri=uri,
                title=enriched.title,
                description=enriched.description,
                summary=enriched.summary,
                topics=enriched.topics,
                entities=enriched.entities,
                version_tag=version_tag,
            )
            if not updated:
                return uri, False, "row vanished during update"
            logger.info("reenrich OK %s in %.1fs", uri, elapsed)
            return uri, True, None
        except Exception as exc:
            logger.exception("reenrich FAILED %s", uri)
            return uri, False, f"{type(exc).__name__}: {exc}"


async def run(
    *,
    version_tag: str,
    source_type: SourceType | None,
    limit: int | None,
    concurrency: int,
) -> dict:
    repo = ContentRepository()
    uris = repo.list_uris_for_reenrichment(source_type, version_tag, limit=limit)
    total = len(uris)
    logger.info("Found %d URIs to re-enrich (source=%s, tag=%s)",
                total, source_type, version_tag)
    if not uris:
        return {"total": 0, "succeeded": 0, "failed": 0}

    sem = asyncio.Semaphore(concurrency)
    succeeded = 0
    failed = 0
    failures: list[tuple[str, str]] = []
    started_at = datetime.now(timezone.utc)

    tasks = [
        asyncio.create_task(_reenrich_one(uri, repo, version_tag, sem))
        for uri in uris
    ]

    last_report = time.monotonic()
    for fut in asyncio.as_completed(tasks):
        uri, ok, err = await fut
        if ok:
            succeeded += 1
        else:
            failed += 1
            if err:
                failures.append((uri, err))
        done = succeeded + failed
        if time.monotonic() - last_report > 5.0 or done == total:
            _report_progress(
                done / total,
                f"{done}/{total} done ({succeeded} ok, {failed} failed)",
            )
            last_report = time.monotonic()

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures[:50],
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--tag", required=True,
        help="Version tag stamped on content_metadata._enrichment_version. "
             "Pick a stable identifier per re-enrichment pass (e.g. hyde_2026_06).",
    )
    p.add_argument(
        "--source", choices=[s.value for s in SourceType],
        help="Limit to one SourceType. Omit to scan all source types.",
    )
    p.add_argument(
        "--limit", type=int,
        help="Cap rows processed. Useful for smoke tests.",
    )
    p.add_argument(
        "--concurrency", type=int, default=3,
        help="Max in-flight enrichments. Each enrich() = 3 sequential LLM calls.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Count matching rows and exit without enriching.",
    )
    p.add_argument(
        "--confirm", default="",
        help="Required for non-dry-run execution. Pass 'YES PROCEED' exactly.",
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    signal.signal(signal.SIGTERM, _handle_sigterm)

    src = SourceType(args.source) if args.source else None

    if args.dry_run:
        repo = ContentRepository()
        uris = repo.list_uris_for_reenrichment(src, args.tag, limit=args.limit)
        logger.info("DRY RUN — would re-enrich %d URIs (source=%s, tag=%s)",
                    len(uris), src, args.tag)
        _write_status({
            "mode": "dry-run", "source": str(src), "tag": args.tag,
            "match_count": len(uris),
        })
        return

    if args.confirm != "YES PROCEED":
        logger.error("Refusing to run without --confirm 'YES PROCEED'.")
        sys.exit(2)

    result = asyncio.run(run(
        version_tag=args.tag,
        source_type=src,
        limit=args.limit,
        concurrency=args.concurrency,
    ))
    _write_status({
        "mode": "execute",
        "source": str(src),
        "tag": args.tag,
        **result,
    })
    logger.info("Done. %s", {k: v for k, v in result.items() if k != "failures"})
    if result["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
