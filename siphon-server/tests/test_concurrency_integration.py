from __future__ import annotations

import asyncio

import pytest
from unittest.mock import patch
from unittest.mock import MagicMock

from siphon_api.api.batch_extract import BatchExtractRequest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_20_concurrent_extracts_do_not_exhaust_pool_or_oom():
    """AC 9: concurrent batch extract of 20 PDFs does not exhaust the Postgres
    connection pool or raise an OOM error."""
    from siphon_server.services.batch_extract_service import batch_extract_siphon_service

    mock_content = MagicMock()
    mock_content.text = "extracted text from pdf"

    async def slow_extract(source, action):
        await asyncio.sleep(0.05)
        return mock_content

    with patch(
        "siphon_server.services.batch_extract_service.SiphonPipeline"
    ) as MockPipeline:
        instance = MagicMock()
        instance.process = slow_extract
        MockPipeline.return_value = instance

        sources = [f"doc_{i}.pdf" for i in range(20)]
        req = BatchExtractRequest(sources=sources, max_concurrent=20)
        resp = await batch_extract_siphon_service(req)

    assert len(resp.results) == 20
    assert all(r.error is None for r in resp.results), [
        r.error for r in resp.results if r.error
    ]
