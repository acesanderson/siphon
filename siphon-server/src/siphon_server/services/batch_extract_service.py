from __future__ import annotations

import asyncio
import logging

from siphon_api.api.batch_extract import BatchExtractRequest
from siphon_api.api.batch_extract import BatchExtractResponse
from siphon_api.api.batch_extract import BatchExtractResult
from siphon_api.enums import ActionType
from siphon_server.core.pipeline import SiphonPipeline

logger = logging.getLogger(__name__)


async def batch_extract_siphon_service(req: BatchExtractRequest) -> BatchExtractResponse:
    """Run up to req.max_concurrent pipeline extractions concurrently.

    Each source is run with ActionType.EXTRACT (text only, no enrichment).
    Errors are caught per-source and returned in BatchExtractResult.error so
    that one failure does not abort the entire batch.
    """
    semaphore = asyncio.Semaphore(req.max_concurrent)
    pipeline = SiphonPipeline()

    async def _extract_one(source: str) -> BatchExtractResult:
        async with semaphore:
            try:
                content = await pipeline.process(source, ActionType.EXTRACT)
                return BatchExtractResult(source=source, text=content.text)
            except Exception as exc:
                logger.warning("batch_extract failed for %s: %s", source, exc)
                return BatchExtractResult(source=source, error=str(exc))

    tasks = [_extract_one(s) for s in req.sources]
    results = await asyncio.gather(*tasks)
    return BatchExtractResponse(results=list(results))
