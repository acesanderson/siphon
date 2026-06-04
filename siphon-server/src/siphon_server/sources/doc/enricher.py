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
from siphon_api.models import ContentData, EnrichedData
from siphon_server.config import settings

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.CRITICAL + 10)

SOURCE_DIR = Path(__file__).parent
PROMPTS_DIR = SOURCE_DIR / "prompts"
PREFERRED_MODEL = settings.default_model

_VARIANTS = ("code", "data", "presentation", "prose")
_DESCRIPTION_MODEL = "gpt-oss:latest"
_DESCRIPTION_HOST = "bywater"


class DocEnricher(EnricherStrategy):
    """
    Enrich Doc content with LLM. Routes by MIME type to one of four variants
    (code, data, presentation, prose). Each variant has its own summary
    guideline and HyDE-shaped description guideline. Sequential:
    summary -> description -> title.
    """

    source_type: SourceType = SourceType.DOC

    def __init__(self):
        self.title_template = Prompt((PROMPTS_DIR / "title.jinja2").read_text())
        self.summary_guidelines: dict[str, Prompt] = {
            v: Prompt((SOURCE_DIR / f"{v}_guideline.jinja2").read_text())
            for v in _VARIANTS
        }
        self.description_guidelines: dict[str, Prompt] = {
            v: Prompt((SOURCE_DIR / f"{v}_description_guideline.jinja2").read_text())
            for v in _VARIANTS
        }

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        variant = self._route(content.metadata["mime_type"])
        summary = await self._summarize(variant, content.text, content.metadata)
        description = await self._describe(variant, summary, content.metadata)
        title = await self._titleize(description, preferred_model)

        return EnrichedData(
            source_type=SourceType.DOC,
            title=title,
            description=description,
            summary=summary,
            topics=[],
            entities=[],
        )

    @staticmethod
    def _route(mime_type: str) -> str:
        if mime_type.startswith("text/x-"):
            return "code"
        if "spreadsheet" in mime_type or mime_type == "text/csv":
            return "data"
        if "presentation" in mime_type:
            return "presentation"
        return "prose"

    async def _summarize(
        self, variant: str, text: str, metadata: dict[str, Any]
    ) -> str:
        guideline = self.summary_guidelines[variant].render({"metadata": metadata})
        text_input = _TextInput(
            data=text, source_id=f"doc:{variant}", guideline=guideline
        )
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})

    async def _describe(
        self, variant: str, summary: str, metadata: dict[str, Any]
    ) -> str:
        guideline = self.description_guidelines[variant].render({"metadata": metadata})
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

    def _generate_topics(self, input_variables: dict[str, Any]) -> list[str]: ...

    def _generate_entities(self, input_variables: dict[str, Any]) -> list[str]: ...
