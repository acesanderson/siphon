from __future__ import annotations

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
SOURCE_DIR = Path(__file__).parent
PROMPTS_DIR = SOURCE_DIR / "prompts"
GUIDELINE_PATH = SOURCE_DIR / "guideline.jinja2"
DESCRIPTION_GUIDELINE_PATH = SOURCE_DIR / "description_guideline.jinja2"
PREFERRED_MODEL = settings.default_model

_DESCRIPTION_MODEL = "gpt-oss:latest"
_DESCRIPTION_HOST = "bywater"


class EmailEnricher(EnricherStrategy):
    """
    Enrich email content with LLM.

    Summary path: RoutingSummarizer + PRODUCTION_ROUTING.
    Description path: HyDE-shaped, gpt-oss/bywater one-shot over the summary.
    Sequential: summary -> description -> title.
    """

    source_type: SourceType = SourceType.EMAIL

    def __init__(self):
        self.title_template = Prompt((PROMPTS_DIR / "title.jinja2").read_text())
        self.guideline_template = Prompt(GUIDELINE_PATH.read_text())
        self.description_guideline_template = Prompt(
            DESCRIPTION_GUIDELINE_PATH.read_text()
        )

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        summary = await self._summarize(content.text, content.metadata)
        description = await self._describe(summary, content.metadata)
        title = await self._titleize(description, preferred_model)

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
        text_input = _TextInput(data=text, source_id="email", guideline=guideline)
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})

    async def _describe(self, summary: str, metadata: dict[str, Any]) -> str:
        guideline = self.description_guideline_template.render({"metadata": metadata})
        prompt = f"{guideline}\n\n<summary>\n{summary}\n</summary>"
        model = RemoteModelAsync(model=_DESCRIPTION_MODEL, host_alias=_DESCRIPTION_HOST)
        params = GenerationParams(model=_DESCRIPTION_MODEL)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")
        result = await model.query(query_input=prompt, params=params, options=options)
        return str(result.content)

    async def _titleize(self, description: str, preferred_model: str) -> str:
        prompt = self.title_template.render({"description": description})
        model = RemoteModelAsync(model=preferred_model)
        params = GenerationParams(model=preferred_model)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")
        result = await model.query(query_input=prompt, params=params, options=options)
        return str(result.content)
