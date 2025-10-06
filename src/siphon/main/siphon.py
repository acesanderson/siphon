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
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conduit.message.imagemessage import ImageMessage

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
    # Grab local flag -- do we use cloud or SiphonServer?
    # Validate input
    elif isinstance(cli_params, str):
        source = cli_params
        cache_options = "c"  # Default, cache it.
        tags = []
    elif isinstance(cli_params, CLIParams):
        source = cli_params.source
        cache_options = cli_params.cache_options
        tags = cli_params.tags
        cloud = cli_params.cloud
    else:
        raise TypeError(
            f"Expected a string or CLIParams object, got: {cli_params.__class__.__name__}"
        )

    # 1. Parse source into structured URI
    uri = URI.from_source(source)
    if not uri:
        raise ValueError(f"Invalid source: {source}. Must be a valid file path or URL.")

    if cache_options == "c":
        logger.info(f"Checking cache for URI: {uri.uri}")
        try:
            cached_content = get_cached_content(uri.uri)
            if cached_content:
                logger.info("Cache HIT! Returning cached content")
                return cached_content
            else:
                logger.info("Cache MISS - no content found")
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

    # 3. Generate LLM context from the URI (retrieving text content)
    logger.info("Generating context from URI...")
    context = Context.from_uri(uri)

    # 4. Generate SyntheticData (post-processing)
    logger.info(f"Generating synthetic data from context...")
    synthetic_data = SyntheticData.from_context(context, cloud=cloud)
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

    if cache_options in ["c", "r"]:
        try:
            logger.info(f"Attempting to cache content for URI: {uri.uri}")
            result = cache_processed_content(processed_content)
            logger.info(f"Successfully cached with key: {result}")
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    # 7. Return the processed content
    return processed_content
