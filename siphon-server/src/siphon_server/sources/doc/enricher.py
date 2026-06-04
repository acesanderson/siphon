from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, override

from conduit.config import settings as conduit_settings
from conduit.core.model.model_remote import RemoteModelAsync
from conduit.core.prompt.prompt import Prompt
from conduit.domain.request.generation_params import GenerationParams
from conduit.strategies.summarize.strategy import _TextInput
from conduit.strategies.summarize.summarizers.routing import (
    PRODUCTION_ROUTING,
    RoutingSummarizer,
)

from siphon_api.enums import SourceType
from siphon_api.interfaces import EnricherStrategy
from siphon_api.models import ContentData, EnrichedData
from siphon_server.config import settings

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.CRITICAL + 10)

PROMPTS_DIR = Path(__file__).parent / "prompts"
DOC_DIR = Path(__file__).parent
PREFERRED_MODEL = settings.default_model


class DocEnricher(EnricherStrategy):
    """
    Enrich Doc content with LLM. Routes by MIME type to one of four variants
    (code, data, presentation, prose). Each variant's summary path uses
    RoutingSummarizer + PRODUCTION_ROUTING with a variant-specific guideline.
    Description path remains the legacy single-call pattern until the HyDE
    description redesign rolls out per siphon-server/dev/retrieval.md.
    """

    source_type: SourceType = SourceType.DOC

    def __init__(self):
        from conduit.core.prompt.prompt_loader import PromptLoader

        self.prompt_loader = PromptLoader(base_dir=PROMPTS_DIR)
        self.guidelines: dict[str, Prompt] = {
            variant: Prompt((DOC_DIR / f"{variant}_guideline.jinja2").read_text())
            for variant in ("code", "data", "presentation", "prose")
        }

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        mime_type = content.metadata["mime_type"]
        if mime_type.startswith("text/x-"):
            variant = "code"
        elif "spreadsheet" in mime_type or mime_type == "text/csv":
            variant = "data"
        elif "presentation" in mime_type:
            variant = "presentation"
        else:
            variant = "prose"
        return await self._enrich_variant(content, variant, preferred_model)

    async def _enrich_variant(
        self, content: ContentData, variant: str, preferred_model: str
    ) -> EnrichedData:
        description_prompt = self.prompt_loader[f"{variant}_description"]
        title_prompt = self.prompt_loader["title"]
        input_variables = {"text": content.text, "metadata": content.metadata}

        model = RemoteModelAsync(model=preferred_model)
        params = GenerationParams(model=preferred_model)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")

        description_str = description_prompt.render(input_variables)
        description_task = model.query(
            query_input=description_str, params=params, options=options
        )
        summary_task = self._summarize(variant, content.text, content.metadata)

        description_result, summary = await asyncio.gather(
            description_task, summary_task
        )
        description = str(description_result.content)

        title_str = title_prompt.render({"description": description})
        title_result = await model.query(
            query_input=title_str, params=params, options=options
        )
        title = str(title_result.content)

        return EnrichedData(
            source_type=SourceType.DOC,
            title=title,
            description=description,
            summary=summary,
            topics=[],
            entities=[],
        )

    async def _summarize(
        self, variant: str, text: str, metadata: dict[str, Any]
    ) -> str:
        guideline = self.guidelines[variant].render({"metadata": metadata})
        text_input = _TextInput(
            data=text, source_id=f"doc:{variant}", guideline=guideline
        )
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})

    def _generate_topics(self, input_variables: dict[str, Any]) -> list[str]: ...

    def _generate_entities(self, input_variables: dict[str, Any]) -> list[str]: ...
