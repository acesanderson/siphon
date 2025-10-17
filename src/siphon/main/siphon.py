"""
Updated main/siphon.py with PostgreSQL cache integration
"""

from siphon.data.uri import URI
from siphon.data.context import Context
from siphon.data.synthetic_data import SyntheticData
from siphon.cli.cli_params import CLIParams
from siphon.data.processed_content import ProcessedContent
from siphon.database.postgres.PGRES_processed_content import (
    get_cached_content,
    cache_processed_content,
)
from siphon.logs.logging_config import get_logger
from siphon.logs.tracer import tracer
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conduit.message.imagemessage import ImageMessage

tracer.enabled = True
logger = get_logger(__name__)


def siphon(cli_params: CLIParams | Path | str) -> ProcessedContent:
    """
    Siphon orchestrates the process of converting a source string (file path or URL).
    Now includes PostgreSQL caching for performance.
    """
    cloud = cli_params.cloud if isinstance(cli_params, CLIParams) else False
    # Coerce Path to string
    if isinstance(cli_params, Path):
        source = str(cli_params)
        cache_options = "c"
        tags = []
        tracer.trace_step("1. Source Path", source, "str")
    # Grab local flag -- do we use cloud or SiphonServer?
    # Validate input
    elif isinstance(cli_params, str):
        source = cli_params
        cache_options = "c"  # Default, cache it.
        tags = []
        tracer.trace_step("1. Source String", source, "str")
    elif isinstance(cli_params, CLIParams):
        source = cli_params.source
        cache_options = cli_params.cache_options
        tags = cli_params.tags
        cloud = cli_params.cloud
        tracer.trace_step("1. CLI Params", cli_params, "CLIParams")
    else:
        raise TypeError(
            f"Expected a string or CLIParams object, got: {cli_params.__class__.__name__}"
        )
    # 1. Parse source into structured URI
    uri = URI.from_source(source)
    if not uri:
        raise ValueError(f"Invalid source: {source}. Must be a valid file path or URL.")

    tracer.trace_step("2. URI", uri, "URI")

    if cache_options == "c":
        logger.info(f"Checking cache for URI: {uri.uri}")
        try:
            cached_content = get_cached_content(uri.uri)
            if cached_content:
                logger.info("Cache HIT! Returning cached content")
                tracer.trace_step("Cache HIT", cached_content, "ProcessedContent")
                return cached_content
            else:
                logger.info("Cache MISS - no content found")
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

    # 3. Generate LLM context from the URI (retrieving text content)
    logger.info("Generating context from URI...")
    context = Context.from_uri(uri)
    tracer.trace_step("3. Context", context, "Context")

    # 4. Generate SyntheticData (post-processing)
    logger.info(f"Generating synthetic data from context...")
    synthetic_data = SyntheticData.from_context(context, cloud=cloud)
    tracer.trace_step("4. Synthetic Data", synthetic_data, "SyntheticData")
    if not synthetic_data:
        raise ValueError("Failed to generate synthetic data from context.")
    logger.info("Synthetic data generation complete.")

    # 5. Construct ProcessedContent object
    processed_content = ProcessedContent(
        uri=uri,
        llm_context=context,
        synthetic_data=synthetic_data,
        tags=tags or [],
    )
    tracer.trace_step("5. Processed Content", processed_content, "ProcessedContent")

    if cache_options in ["c", "r"]:
        try:
            logger.info(f"Attempting to cache content for URI: {uri.uri}")
            result = cache_processed_content(processed_content)
            logger.info(f"Successfully cached with key: {result}")
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    # 7. Return the processed content
    return processed_content
