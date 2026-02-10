"""
Add a "test" option which uses a sample asset.
"""

from siphon_api.api.siphon_request import SiphonRequest, SiphonRequestParams
from siphon_api.api.to_siphon_request import create_siphon_request
from siphon_api.api.siphon_response import SiphonResponse
from siphon_api.enums import ActionType
from siphon_api.models import (
    SourceInfo,
    ContentData,
    EnrichedData,
    ProcessedContent,
    PipelineClass,
)
from pathlib import Path
from typing import Literal
import click
import logging
import json
import os
from siphon_client.cli.query import query
from siphon_client.cli.results import results

# Set up logging
log_level = int(os.getenv("PYTHON_LOG_LEVEL", "1"))
levels = {1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
logging.basicConfig(
    level=levels.get(log_level, logging.INFO), format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def parse_source(source: str) -> str:
    try:
        logger.debug(f"Parsing source: {source}")
        path = Path(source)
        if path.exists():
            logger.debug(f"Resolved path: {path.resolve()}")
            return str(path.resolve())
        logger.debug(f"Source is not a file path: {source}")
        return source
    except Exception:
        logger.debug(f"Source is not a file path: {source}")
        return source


def print_output(output_string: str):
    output_string = "\n\n-----------------------------------------\n\n" + output_string
    output_string += "\n\n-----------------------------------------"
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console()
    output = Markdown(output_string)
    console.print(output)


@click.group()
def siphon():
    """
    Process, persist, or extract content from various sources.
    """
    ...


@siphon.command()
@click.argument("source")
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["st", "u", "c", "m", "t", "d", "s", "id", "json"]),
    default="s",
    help="Type to return: [st] source type, [u] url, [c] content, [m] metadata, [t] title, [d] description, [s] summary, [id] uri, [json] full json.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable caching for this request",
)
def gulp(
    source: str,
    return_type: Literal["st", "u", "c", "m", "t", "d", "s", "id", "json"],
    no_cache: bool,
):
    """
    Process a source and persist the results (e.g., DB, embeddings).
    This is also an importable function for programmatic use (if you want a ProcessedContent object).
    """
    logger.info(f"Received source: {source}")
    source = parse_source(source)
    params: SiphonRequestParams = SiphonRequestParams(
        action=ActionType.GULP, use_cache=not no_cache
    )
    request: SiphonRequest = create_siphon_request(
        source=source,
        request_params=params,
    )  # Note the double negative for no_cache
    logger.debug("Loading HeadwaterClient")
    from headwater_client.client.headwater_client import HeadwaterClient
    client = HeadwaterClient()
    logger.info("Processing request")
    response: SiphonResponse = client.siphon.process(request)
    payload: PipelineClass = response.payload
    assert isinstance(payload, ProcessedContent), (
        f"Expected ProcessedContent, got {type(payload)}"
    )
    logger.info("Processing complete")
    # Prepare output -- either string or JSON
    output_string = ""
    output_json = ""
    # Route based on return_type
    match return_type:
        case "st":
            output_string = payload.source_type
        case "u":
            output_string = payload.source.original_source
        case "c":
            output_string = payload.text
        case "m":
            output_string = ""
            output_json = json.dumps(payload.metadata, indent=2)
        case "t":
            output_string = payload.title
        case "d":
            output_string = payload.description
        case "s":
            output_string = payload.summary
        case "id":
            output_string = payload.uri
        case "json":
            output_json = payload.model_dump_json(indent=2)
        case _:
            raise ValueError(f"Unsupported return type: {return_type}")
    # Print output
    if output_string:
        print_output(output_string)
    if output_json:
        from rich.console import Console

        console = Console()
        console.print(output_json)


@siphon.command()
@click.argument("source")
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["u", "st"]),
    default="u",
    help="Type to return: [u] URI, [st] source type.",
)
def parse(source: str, return_type: Literal["u", "st"]):
    """
    Parse a source and return the resolved URI (ephemeral).
    """
    logger.info(f"Received source for parsing: {source}")
    source = parse_source(source)
    params: SiphonRequestParams = SiphonRequestParams(
        action=ActionType.PARSE,
    )
    request: SiphonRequest = create_siphon_request(
        source=source,
        request_params=params,
    )
    logger.debug("Loading HeadwaterClient")
    from headwater_client.client.headwater_client import HeadwaterClient
    client = HeadwaterClient()
    logger.info("Processing request")
    response: SiphonResponse = client.siphon.process(request)
    payload: PipelineClass = response.payload
    assert isinstance(payload, SourceInfo), f"Expected SourceInfo, got {type(payload)}"
    logger.info("Processing complete")
    # Display output based on return_type
    match return_type:
        case "u":
            output_string = payload.uri
        case "st":
            output_string = payload.source_type

    print_output(output_string)


@siphon.command()
@click.argument("source")
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["c", "m", "to"]),
    default="c",
    help="Type to return: [c]ontent, [m]etadata, [to]ken_count.",
)
def extract(source: str, return_type: Literal["c", "m", "to"]):
    """
    Extract content from a source without persisting (ephemeral).
    """
    logger.info(f"Received source for extraction: {source}")
    source = parse_source(source)
    # Two possible actions here
    if return_type == "to":
        action = ActionType.TOKENIZE
    else:
        action = ActionType.EXTRACT
    # Build request
    params: SiphonRequestParams = SiphonRequestParams(action=action)
    request: SiphonRequest = create_siphon_request(
        source=source,
        request_params=params,
    )
    logger.debug("Loading HeadwaterClient")
    from headwater_client.client.headwater_client import HeadwaterClient
    client = HeadwaterClient()
    logger.info("Processing request")
    response: SiphonResponse = client.siphon.process(request)
    payload: PipelineClass = response.payload
    assert isinstance(payload, ContentData), (
        f"Expected ContentData, got {type(payload)}"
    )
    logger.info("Processing complete")
    # Display output based on return_type
    match return_type:
        case "c":
            print_output(payload.text)
        case "to":
            assert payload.token_count > 0, "Returned token count is 0."
            print_output(str(payload.token_count))
        case "m":
            from rich.console import Console
            from rich.markdown import Markdown

            console = Console()
            output_json = json.dumps(payload.metadata, indent=2)
            console.print(output_json)


@siphon.command()
@click.argument("source")
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["s", "d", "t"]),
    default="s",
    help="Type to return: [s]ummary, [d]escription, [t]itle.",
)
def enrich(source: str, return_type: Literal["s", "d", "t"]):
    """
    Enrich a source without persisting (ephemeral).
    """
    logger.info(f"Received source for enrichment: {source}")
    source = parse_source(source)
    params: SiphonRequestParams = SiphonRequestParams(
        action=ActionType.ENRICH,
    )
    request: SiphonRequest = create_siphon_request(
        source=source,
        request_params=params,
    )
    logger.debug("Loading HeadwaterClient")
    from headwater_client.client.headwater_client import HeadwaterClient
    client = HeadwaterClient()
    logger.info("Processing request")
    response: SiphonResponse = client.siphon.process(request)
    payload: PipelineClass = response.payload
    assert isinstance(payload, EnrichedData), (
        f"Expected EnrichedData, got {type(payload)}"
    )
    logger.info("Processing complete")
    match return_type:
        case "s":
            output_string = payload.summary
        case "d":
            output_string = payload.description
        case "t":
            output_string = payload.title

    print_output(output_string)


# Register the query and results commands
siphon.add_command(query)
siphon.add_command(results)


def main():
    siphon()


if __name__ == "__main__":
    main()
