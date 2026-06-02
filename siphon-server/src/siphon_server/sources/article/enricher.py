from siphon_server.config import settings
from siphon_api.interfaces import EnricherStrategy
from siphon_api.models import ContentData, EnrichedData
from siphon_api.enums import SourceType
from typing import override, Any
from pathlib import Path
import asyncio
import logging

from conduit.core.model.model_remote import RemoteModelAsync
from conduit.domain.request.generation_params import GenerationParams
from conduit.config import settings as conduit_settings
from conduit.strategies.summarize.strategy import _TextInput
from conduit.strategies.summarize.summarizers.routing import (
    PRODUCTION_ROUTING,
    RoutingSummarizer,
)

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.CRITICAL + 10)

PROMPTS_DIR = Path(__file__).parent / "prompts"
GUIDELINE_PATH = Path(__file__).parent / "guideline.jinja2"
PREFERRED_MODEL = settings.default_model


class ArticleEnricher(EnricherStrategy):
    """
    Enrich Article content with LLM.

    Summary path: routes by token count to a tested SummarizationProfile
    in conduit's PRODUCTION_ROUTING. Long-form articles transparently use
    RollingRefine + a guideline-aware format pass; short articles use
    OneShot. The guideline lives in guideline.jinja2 alongside this module.

    Description path: unchanged single one-shot call. Descriptions are
    short, no routing needed.
    """

    source_type: SourceType = SourceType.ARTICLE

    def __init__(self):
        from conduit.core.prompt.prompt_loader import PromptLoader
        from conduit.core.prompt.prompt import Prompt

        self.prompt_loader = PromptLoader(base_dir=PROMPTS_DIR)
        self.guideline_template = Prompt(GUIDELINE_PATH.read_text())
        logger.debug(f"Loaded prompts: {self.prompt_loader.keys}")

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        logger.info("Enriching Article content")
        text = content.text
        metadata = content.metadata
        _ = content.metadata.pop("raw_text", None)
        input_variables = {"text": text, "metadata": metadata}
        title = content.metadata["title"]
        logger.info(f"Using existing title: {title}")

        description_task = self._describe(input_variables, preferred_model)
        summary_task = self._summarize(text, metadata)

        description, summary = await asyncio.gather(description_task, summary_task)

        logger.info("Generated description and summary")
        return EnrichedData(
            source_type=SourceType.ARTICLE,
            title=title,
            description=description,
            summary=summary,
            topics=[],
            entities=[],
        )

    async def _describe(
        self, input_variables: dict[str, Any], preferred_model: str
    ) -> str:
        prompt = self._generate_description_prompt(input_variables)
        model = RemoteModelAsync(model=preferred_model)
        params = GenerationParams(model=preferred_model)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")
        result = await model.query(query_input=prompt, params=params, options=options)
        return str(result.content)

    async def _summarize(self, text: str, metadata: dict[str, Any]) -> str:
        # Guideline is rendered Siphon-side with metadata, then handed to
        # conduit as opaque text. preferred_model is intentionally ignored
        # here: routing picks the model based on document token count.
        guideline = self.guideline_template.render({"metadata": metadata})
        text_input = _TextInput(data=text, source_id="article", guideline=guideline)
        return await RoutingSummarizer()(text_input, {"routing": PRODUCTION_ROUTING})

    def _generate_description_prompt(self, input_variables: dict[str, Any]) -> str:
        prompt = self.prompt_loader["article_description"]
        return prompt.render(input_variables)


if __name__ == "__main__":
    from siphon_server.sources.article.parser import ArticleParser
    from siphon_server.sources.article.extractor import ArticleExtractor

    article_url = (
        "https://sgoel.dev/posts/10-years-of-personal-finances-in-plain-text-files/"
    )
    parser = ArticleParser()
    source_info = parser.parse(article_url)
    extractor = ArticleExtractor()
    content_data = extractor.extract(source_info)
    enricher = ArticleEnricher()

    enriched_data = asyncio.run(enricher.enrich(content_data))
    print(enriched_data)
