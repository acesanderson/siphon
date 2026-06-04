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
from siphon_api.models import ContentData
from siphon_api.models import EnrichedData
from siphon_server.config import settings

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"
GUIDELINE_PATH = Path(__file__).parent / "guideline.jinja2"
PREFERRED_MODEL = settings.default_model


class ArxivEnricher(EnricherStrategy):
    """Enrich arXiv abstract content with LLM. Summary uses RoutingSummarizer."""

    source_type: SourceType = SourceType.ARXIV

    def __init__(self):
        from conduit.core.prompt.prompt_loader import PromptLoader

        self.prompt_loader = PromptLoader(base_dir=PROMPTS_DIR)
        self.guideline_template = Prompt(GUIDELINE_PATH.read_text())

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        model = RemoteModelAsync(model=preferred_model)
        params = GenerationParams(model=preferred_model)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")

        input_variables = {"text": content.text, "metadata": content.metadata}
        description_str = self.prompt_loader["arxiv_description"].render(input_variables)

        description_task = model.query(
            query_input=description_str, params=params, options=options
        )
        summary_task = self._summarize(content.text, content.metadata)

        description_result, summary = await asyncio.gather(
            description_task, summary_task
        )
        description = str(description_result.content)

        title_str = self.prompt_loader["title"].render({"description": description})
        title_result = await model.query(
            query_input=title_str, params=params, options=options
        )
        title = str(title_result.content)

        return EnrichedData(
            source_type=self.source_type,
            title=title,
            description=description,
            summary=summary,
            topics=[],
            entities=[],
        )

    async def _summarize(self, text: str, metadata: dict[str, Any]) -> str:
        guideline = self.guideline_template.render({"metadata": metadata})
        text_input = _TextInput(data=text, source_id="arxiv", guideline=guideline)
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})
