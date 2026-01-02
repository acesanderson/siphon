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

logger = logging.getLogger(__name__)
# Constants
PROMPTS_DIR = Path(__file__).parent / "prompts"
PREFERRED_MODEL = settings.default_model


class AudioEnricher(EnricherStrategy):
    """
    Enrich Audio content with LLM
    """

    source_type: SourceType = SourceType.AUDIO

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
        """
        Enrich audio transcript content with LLM-generated metadata.

            Generates a semantic description, summary, and title for audio content by rendering
            audio-specific prompts through a language model. Uses async batch processing for
            description and summary, then synchronously generates a title from the description.

            Args:
                content: ContentData containing transcript text and file metadata to enrich.

            Returns:
                EnrichedData with generated title, description, summary, and empty topics/entities lists.

            Raises:
                AssertionError: If LLM responses are not of type Response or if title generation fails.
        """
        if content.source_type != self.source_type:
            raise ValueError(
                f"AudioEnricher can only enrich content of type {self.source_type}, got {content.source_type} instead."
            )
        logger.info("Enriching Audio content with specialized prompts")
        description_prompt = self.prompt_loader["audio_description"]
        summary_prompt = self.prompt_loader["audio_summary"]
        title_prompt = self.prompt_loader["title"]
        
        # Input variables for prompts
        input_variables = {"text": content.text, "metadata": content.metadata}
        source_type = SourceType.AUDIO
        
        # Render description and summary prompts
        description_prompt_str = description_prompt.render(input_variables)
        summary_prompt_str = summary_prompt.render(input_variables)
        logger.info("Generated description and summary prompts")
        
        # Set up model and options
        model = ModelAsync(model=preferred_model)
        params = GenerationParams(model=preferred_model)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")
        
        # Run async calls for description and summary
        import asyncio
        description_task = model.query(
            query_input=description_prompt_str, params=params, options=options
        )
        summary_task = model.query(
            query_input=summary_prompt_str, params=params, options=options
        )
        
        description_result, summary_result = await asyncio.gather(
            description_task, summary_task
        )
        
        description = str(description_result.content)
        summary = str(summary_result.content)
        
        # Generate title from description
        title_prompt_str = title_prompt.render({"description": description})
        title_result = await model.query(
            query_input=title_prompt_str, params=params, options=options
        )
        title = str(title_result.content)
        logger.info("Generated title, description, and summary")

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

    def _generate_topics(self, input_variables: dict[str, Any]) -> list[str]: ...

    def _generate_entities(self, input_variables: dict[str, Any]) -> list[str]: ...


if __name__ == "__main__":
    from siphon_server.example import EXAMPLE_MP3, EXAMPLE_WAV
    from siphon_server.sources.audio.parser import AudioParser
    from siphon_server.sources.audio.extractor import AudioExtractor

    parser = AudioParser()
    for example in [EXAMPLE_MP3, EXAMPLE_WAV]:
        if parser.can_handle(str(example)):
            info = parser.parse(str(example))
            print(info.model_dump_json(indent=4))

    extractor = AudioExtractor()
    for example in [EXAMPLE_MP3, EXAMPLE_WAV]:
        if parser.can_handle(str(example)):
            info = parser.parse(str(example))
            try:
                content = extractor.extract(info)
                print(content.model_dump_json(indent=4))
            except NotImplementedError:
                print(f"Extraction not implemented for {info.source_type}")

    enricher = AudioEnricher()
    for example in [EXAMPLE_MP3, EXAMPLE_WAV]:
        if parser.can_handle(str(example)):
            info = parser.parse(str(example))
            try:
                content = extractor.extract(info)
                enriched = enricher.enrich(content)
                print(enriched.model_dump_json(indent=4))
            except NotImplementedError:
                print(f"Enrichment not implemented for {info.source_type}")
