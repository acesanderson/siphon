from siphon_server.config import settings
from siphon_api.interfaces import EnricherStrategy
from siphon_api.models import ContentData, EnrichedData
from siphon_api.enums import SourceType
from typing import override, Any
from pathlib import Path
import logging

# Import new Conduit async API
from conduit.core.model.model_async import ModelAsync
from conduit.domain.request.generation_params import GenerationParams
from conduit.domain.config.conduit_options import ConduitOptions
from conduit.config import settings as conduit_settings

# Set up logging
logger = logging.getLogger(__name__)
# Set root logger to silent
logging.getLogger().setLevel(logging.CRITICAL + 10)

# Constants
PROMPTS_DIR = Path(__file__).parent / "prompts"
PREFERRED_MODEL = settings.default_model


class YouTubeEnricher(EnricherStrategy):
    """
    Enrich YouTube content with LLM.
    """

    source_type: SourceType = SourceType.YOUTUBE

    def __init__(self):
        from conduit.core.prompt.prompt_loader import PromptLoader

        # Load prompts packaged with this module
        self.prompt_loader = PromptLoader(
            base_dir=PROMPTS_DIR,
        )
        logger.debug(f"Loaded prompts: {self.prompt_loader.keys}")

    @override
    async def enrich(
        self, content: ContentData, preferred_model: str = PREFERRED_MODEL
    ) -> EnrichedData:
        logger.info("Enriching YouTube content")
        input_variables = {"text": content.text, "metadata": content.metadata}
        source_type = SourceType.YOUTUBE
        title = self._generate_title(input_variables)  # This is already in metadata
        logger.info(f"Generated title: {title}")

        # Generate description and summary concurrently
        description_prompt = self._generate_description_prompt(input_variables)
        summary_prompt = self._generate_summary_prompt(input_variables)

        # Set up model and options
        model = ModelAsync(model=preferred_model)
        params = GenerationParams(model=preferred_model)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")

        # Run async calls for description and summary
        import asyncio

        description_task = model.query(
            query_input=description_prompt, params=params, options=options
        )
        summary_task = model.query(
            query_input=summary_prompt, params=params, options=options
        )

        description_result, summary_result = await asyncio.gather(
            description_task, summary_task
        )

        description = str(description_result.content)
        summary = str(summary_result.content)

        logger.info(f"Generated description and summary")

        # Construct enriched data
        enriched_data = EnrichedData(
            source_type=source_type,
            title=title,
            description=description,
            summary=summary,
            topics=[],
            entities=[],
        )
        logger.info("Enrichment complete")
        return enriched_data

    def _generate_title(self, input_variables: dict[str, Any]) -> str:
        title = input_variables["metadata"]["title"]
        return title

    def _generate_description_prompt(self, input_variables: dict[str, Any]) -> str:
        print(self.prompt_loader.keys)
        prompt = self.prompt_loader["description"]
        return prompt.render(input_variables)

    def _generate_summary_prompt(self, input_variables: dict[str, Any]) -> str:
        prompt = self.prompt_loader["summary"]
        return prompt.render(input_variables)

    def _generate_topics(self, input_variables: dict[str, Any]) -> list[str]: ...

    def _generate_entities(self, input_variables: dict[str, Any]) -> list[str]: ...


if __name__ == "__main__":
    from siphon_server.sources.youtube.parser import YouTubeParser
    from siphon_server.sources.youtube.extractor import YouTubeExtractor

    parser = YouTubeParser()
    test_url = "https://www.youtube.com/watch?v=ksjzI-8Rz2w"
    source_info = parser.parse(test_url)
    extractor = YouTubeExtractor()
    content_data = extractor.extract(source_info)
    import asyncio

    enricher = YouTubeEnricher()
    enriched_data = asyncio.run(enricher.enrich(content_data))
    print(enriched_data)
