"""HyDE generation and query embedding for hybrid retrieval.

HyDE (Hypothetical Document Embeddings, Gao et al. 2022) is a query
transformation step: instead of embedding the raw query, the LLM is asked
to write a passage that would answer the query, and that hypothetical
passage is embedded. The retrieval then matches stored descriptions
(which were also written in answer-voice via the HyDE description rollout)
against an answer-voice query embedding, which lands in better semantic
territory than the question-voice raw query.

Disabled via the --no-hyde CLI flag, in which case the raw query is
embedded directly. Faster (no LLM call), lower quality on conversational
queries.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


_HYDE_PROMPT = """Write a passage that would answer the following question:

{query}

The passage should be one to three paragraphs, factually framed, in answer voice.
Do not preface with "Here is..." or "The passage is...". Return only the passage."""


def hyde_passage(query: str) -> str:
    """Generate a HyDE hypothetical answer for the query.

    Synchronous wrapper around the async conduit call. One gpt-oss/bywater
    generation per call. Adds ~1-3s latency in exchange for higher-quality
    retrieval on natural-language queries.
    """
    return asyncio.run(_hyde_passage_async(query))


async def _hyde_passage_async(query: str) -> str:
    from conduit.config import settings as conduit_settings
    from conduit.core.model.model_remote import RemoteModelAsync
    from conduit.domain.request.generation_params import GenerationParams

    prompt = _HYDE_PROMPT.format(query=query)
    model = RemoteModelAsync(model="gpt-oss:latest", host_alias="bywater")
    params = GenerationParams(model="gpt-oss:latest")
    options = conduit_settings.default_conduit_options()
    options.cache = conduit_settings.default_cache(project_name="siphon")
    result = await model.query(query_input=prompt, params=params, options=options)
    return str(result.content)


def embed_query(text: str) -> list[float]:
    """Embed query text via headwater's quick_embedding endpoint.

    Uses the same model the corpus was embedded with (nomic-embed-text-v1.5).
    A query and the corpus MUST share the embedding model — that's enforced
    here by pinning to SIPHON_EMBED_MODEL_V2 rather than taking model as arg.
    """
    from headwater_api.classes import QuickEmbeddingRequest
    from headwater_api.classes.siphon_classes.requests import SIPHON_EMBED_MODEL_V2
    from headwater_client.client.headwater_client import HeadwaterClient

    client = HeadwaterClient()
    resp = client.embeddings.quick_embedding(
        QuickEmbeddingRequest(query=text, model=SIPHON_EMBED_MODEL_V2)
    )
    return resp.embedding
