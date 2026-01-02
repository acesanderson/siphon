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
from conduit.core.prompt.prompt import Prompt

# Set up logging
logger = logging.getLogger(__name__)
# Set root logger to silent
logging.getLogger().setLevel(logging.CRITICAL + 10)

# Constants
PROMPTS_DIR = Path(__file__).parent / "prompts"
PREFERRED_MODEL = settings.default_model


class DocEnricher(EnricherStrategy):
    """
    Enrich Doc content with LLM
    """

    source_type: SourceType = SourceType.DOC

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
        logger.info("Routing Doc content based on MIME type")
        mime_type = content.metadata["mime_type"]

        # Route to specialized prompt
        if mime_type.startswith("text/x-"):  # Code
            return await self._enrich_code(content, preferred_model)
        elif "spreadsheet" in mime_type or mime_type == "text/csv":
            return await self._enrich_data(content, preferred_model)
        elif "presentation" in mime_type:
            return await self._enrich_presentation(content, preferred_model)
        else:  # Default: prose documents
            return await self._enrich_prose(content, preferred_model)

    async def _enrich_code(self, content: ContentData, preferred_model: str) -> EnrichedData:
        description_prompt = self.prompt_loader["code_description"]
        summary_prompt = self.prompt_loader["code_summary"]
        return await self._enrich_with_prompts(
            content, description_prompt, summary_prompt, preferred_model
        )

    async def _enrich_data(self, content: ContentData, preferred_model: str) -> EnrichedData:
        description_prompt = self.prompt_loader["data_description"]
        summary_prompt = self.prompt_loader["data_summary"]
        return await self._enrich_with_prompts(
            content, description_prompt, summary_prompt, preferred_model
        )

    async def _enrich_presentation(
        self, content: ContentData, preferred_model: str
    ) -> EnrichedData:
        description_prompt = self.prompt_loader["presentation_description"]
        summary_prompt = self.prompt_loader["presentation_summary"]
        return await self._enrich_with_prompts(
            content, description_prompt, summary_prompt, preferred_model
        )

    async def _enrich_prose(self, content: ContentData, preferred_model: str) -> EnrichedData:
        description_prompt = self.prompt_loader["prose_description"]
        summary_prompt = self.prompt_loader["prose_summary"]
        return await self._enrich_with_prompts(
            content, description_prompt, summary_prompt, preferred_model
        )

    async def _enrich_with_prompts(
        self,
        content: ContentData,
        description_prompt: Prompt,
        summary_prompt: Prompt,
        preferred_model: str,
    ) -> EnrichedData:
        logger.info("Enriching Doc content with specialized prompts")
        title_prompt = self.prompt_loader["title"]
        
        # Input variables for prompts
        input_variables = {"text": content.text, "metadata": content.metadata}
        source_type = SourceType.DOC
        
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
