from __future__ import annotations

import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_docling_convert_does_not_block_event_loop():
    """Two concurrent doc extractions must overlap in time, not serialize."""
    from siphon_server.sources.doc.extractor import DocExtractor

    extractor = DocExtractor()
    call_log: list[tuple[str, float]] = []

    def fake_docling_convert(path) -> MagicMock:
        call_log.append(("start", time.monotonic()))
        time.sleep(0.15)  # simulate blocking work
        call_log.append(("end", time.monotonic()))
        result = MagicMock()
        result.document.export_to_markdown.return_value = "# doc"
        result.document.pictures = []
        return result

    fake_metadata = {"file_name": "test.pdf"}

    with patch.object(extractor, "_docling_convert", fake_docling_convert), \
         patch.object(extractor, "_docling_to_markdown", return_value="# doc"), \
         patch.object(extractor, "_generate_metadata", return_value=fake_metadata):
        source_a = MagicMock()
        source_a.original_source = "/tmp/a.pdf"
        source_b = MagicMock()
        source_b.original_source = "/tmp/b.pdf"

        start = time.monotonic()
        await asyncio.gather(
            asyncio.to_thread(extractor.extract, source_a),
            asyncio.to_thread(extractor.extract, source_b),
        )
        elapsed = time.monotonic() - start

    # If truly concurrent, total time < 2 * sleep_time (0.30s)
    assert elapsed < 0.28, f"Extractions appeared to serialize: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_docling_concurrency_limited_by_semaphore():
    """At most docling_vlm_concurrency Docling jobs run simultaneously."""
    import threading
    from siphon_server.sources.doc.extractor import DocExtractor
    from siphon_server.config import settings

    active: list[int] = []
    max_observed = [0]
    lock = threading.Lock()

    def fake_convert(path) -> MagicMock:
        with lock:
            active.append(1)
            max_observed[0] = max(max_observed[0], len(active))
        time.sleep(0.05)
        with lock:
            active.pop()
        result = MagicMock()
        result.document.export_to_markdown.return_value = "# doc"
        result.document.pictures = []
        return result

    original = settings.docling_vlm_concurrency
    settings.docling_vlm_concurrency = 2
    extractor = DocExtractor()  # re-init to pick up new semaphore size

    try:
        with patch.object(extractor, "_docling_convert", fake_convert):
            with patch.object(extractor, "_docling_to_markdown", return_value="# doc"):
                with patch.object(extractor, "_generate_metadata", return_value={"file_name": "test.pdf"}):
                    sources = [MagicMock() for _ in range(6)]
                    for i, s in enumerate(sources):
                        s.uri = f"file:///doc{i}.pdf"
                    await asyncio.gather(*[
                        asyncio.to_thread(extractor.extract, s) for s in sources
                    ])
    finally:
        settings.docling_vlm_concurrency = original

    assert max_observed[0] <= 2, f"Max concurrent was {max_observed[0]}, expected ≤2"
