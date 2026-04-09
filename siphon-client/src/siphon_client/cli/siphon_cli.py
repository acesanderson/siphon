"""
Add a "test" option which uses a sample asset.
"""
from __future__ import annotations

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
import sys
from siphon_client.cli.bulk_extract import bulk_extract
from siphon_client.cli.query import query
from siphon_client.cli.results import results
from siphon_client.cli.traverse import traverse
from siphon_client.cli.sync import sync
from siphon_client.ephemeral import (
    EphemeralInputError,
    build_ephemeral_request,
    read_clipboard,
    read_stdin,
)

# Set up logging
log_level = int(os.getenv("PYTHON_LOG_LEVEL", "1"))
levels = {1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
logging.basicConfig(
    level=levels.get(log_level, logging.INFO), format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

CLIPBOARD_SENTINEL = "@clipboard"


def resolve_ephemeral(
    source: str | None,
    params: SiphonRequestParams,
    fmt: str | None = None,
    extra_args: tuple[str, ...] = (),
) -> SiphonRequest | None:
    """
    Resolve @clipboard or piped stdin to a SiphonRequest.
    Returns None if source is a normal path or URL (caller handles it).
    Exits with code 1 on conflict or resolution error.
    """
    is_clipboard = source == CLIPBOARD_SENTINEL

    if is_clipboard and extra_args:
        click.echo("error: cannot combine @clipboard with a source argument")
        raise SystemExit(1)

    has_stdin = not sys.stdin.isatty()

    if not is_clipboard and not has_stdin:
        return None  # Normal path — caller handles

    if is_clipboard and has_stdin:
        click.echo("error: cannot combine @clipboard with piped stdin", err=True)
        raise SystemExit(1)

    if is_clipboard:
        try:
            raw, ext = read_clipboard()
        except EphemeralInputError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        logger.info(f"[EPHEMERAL] clipboard: ext={ext} bytes={len(raw)}")
        return build_ephemeral_request(raw, ext, "clipboard", params)

    # has_stdin is True
    if source is not None:
        click.echo(
            "error: cannot combine piped input with a source argument", err=True
        )
        raise SystemExit(1)
    try:
        raw, ext = read_stdin(fmt_override=fmt)
    except EphemeralInputError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    logger.info(f"[EPHEMERAL] stdin: ext={ext} bytes={len(raw)}")
    return build_ephemeral_request(raw, ext, "stdin", params)


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
@click.argument("source", default=None, required=False)
@click.argument("extra_args", nargs=-1)
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
@click.option(
    "--format",
    "fmt",
    default=None,
    help="Override type detection (e.g. mp3, png, txt).",
)
def gulp(
    source: str | None,
    extra_args: tuple[str, ...],
    return_type: Literal["st", "u", "c", "m", "t", "d", "s", "id", "json"],
    no_cache: bool,
    fmt: str | None,
):
    """
    Process a source and persist the results (e.g., DB, embeddings).
    This is also an importable function for programmatic use (if you want a ProcessedContent object).
    """
    logger.info(f"Received source: {source}")
    params: SiphonRequestParams = SiphonRequestParams(
        action=ActionType.GULP, use_cache=not no_cache
    )
    request: SiphonRequest | None = resolve_ephemeral(source, params, fmt, extra_args)
    if request is None:
        if source is None:
            click.echo("error: source is required", err=True)
            raise SystemExit(1)
        source = parse_source(source)
        request = create_siphon_request(
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
@click.argument("source", default=None, required=False)
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["u", "st"]),
    default="u",
    help="Type to return: [u] URI, [st] source type.",
)
def parse(source: str | None, return_type: Literal["u", "st"]):
    """
    Parse a source and return the resolved URI (ephemeral).
    """
    logger.info(f"Received source for parsing: {source}")
    params: SiphonRequestParams = SiphonRequestParams(
        action=ActionType.PARSE,
    )
    request: SiphonRequest | None = resolve_ephemeral(source, params)
    if request is None:
        if source is None:
            click.echo("error: source is required", err=True)
            raise SystemExit(1)
        source = parse_source(source)
        request = create_siphon_request(
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
@click.argument("source", default=None, required=False)
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["c", "m", "to"]),
    default="c",
    help="Type to return: [c]ontent, [m]etadata, [to]ken_count.",
)
@click.option(
    "--diarize",
    is_flag=True,
    default=False,
    help="Enable speaker diarization (audio sources only).",
)
@click.option(
    "--format",
    "fmt",
    default=None,
    help="Override type detection (e.g. mp3, png, txt).",
)
def extract(source: str | None, return_type: Literal["c", "m", "to"], diarize: bool, fmt: str | None):
    """
    Extract content from a source without persisting (ephemeral).
    """
    logger.info(f"Received source for extraction: {source}")
    # Two possible actions here
    if return_type == "to":
        action = ActionType.TOKENIZE
    else:
        action = ActionType.EXTRACT
    # Build request
    params: SiphonRequestParams = SiphonRequestParams(action=action, diarize=diarize)
    request: SiphonRequest | None = resolve_ephemeral(source, params, fmt)
    if request is None:
        if source is None:
            click.echo("error: source is required", err=True)
            raise SystemExit(1)
        source = parse_source(source)
        request = create_siphon_request(
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
@click.argument("source", default=None, required=False)
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["s", "d", "t"]),
    default="s",
    help="Type to return: [s]ummary, [d]escription, [t]itle.",
)
def enrich(source: str | None, return_type: Literal["s", "d", "t"]):
    """
    Enrich a source without persisting (ephemeral).
    """
    logger.info(f"Received source for enrichment: {source}")
    params: SiphonRequestParams = SiphonRequestParams(
        action=ActionType.ENRICH,
    )
    request: SiphonRequest | None = resolve_ephemeral(source, params)
    if request is None:
        if source is None:
            click.echo("error: source is required", err=True)
            raise SystemExit(1)
        source = parse_source(source)
        request = create_siphon_request(
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


# Register commands
siphon.add_command(bulk_extract)
siphon.add_command(query)
siphon.add_command(results)
siphon.add_command(traverse)
siphon.add_command(sync)


def main():
    siphon()


if __name__ == "__main__":
    main()
