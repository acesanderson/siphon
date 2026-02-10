"""
Siphon query command - search and retrieve ingested content.

Provides text search, filtering, and various output formats for querying
the Siphon content database.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

import click
from dateutil import parser as date_parser
from rich.table import Table

from siphon_api.enums import SourceType
from siphon_api.models import ProcessedContent, QueryHistory, QueryResultItem
from siphon_client.cli.printer import Printer
from siphon_client.cli.scratchpad import Scratchpad
from siphon_client.client import SiphonClient
from siphon_client.collections.collection import Collection
from siphon_server.database.postgres.repository import QueryHistoryRepository
import time


# Mapping of CLI source type names to SourceType enum
SOURCE_TYPE_MAP = {
    "youtube": SourceType.YOUTUBE,
    "doc": SourceType.DOC,
    "audio": SourceType.AUDIO,
    "web": SourceType.ARTICLE,  # Note: "web" maps to ARTICLE
    "drive": SourceType.DRIVE,
}


def normalize_extension(extension: str | None) -> str | None:
    """
    Normalize file extension by removing leading dot and converting to lowercase.

    Args:
        extension: File extension with or without leading dot (e.g., ".pdf" or "pdf")

    Returns:
        Normalized extension without dot (e.g., "pdf"), or None if input is None

    Examples:
        >>> normalize_extension(".pdf")
        "pdf"
        >>> normalize_extension("PDF")
        "pdf"
        >>> normalize_extension("docx")
        "docx"
    """
    if not extension:
        return None

    normalized = extension.lower().strip()
    if normalized.startswith("."):
        normalized = normalized[1:]

    return normalized if normalized else None


def parse_date_filter(
    date_str: str,
) -> tuple[Literal[">", "<", ">=", "<="], datetime] | None:
    """
    Parse date filter string like '>2024-01-01' or '<2024-12-31'.

    Args:
        date_str: Date string with optional operator prefix

    Returns:
        Tuple of (operator, datetime) or None if parsing fails
    """
    if not date_str:
        return None

    # Extract operator and date string
    operator: Literal[">", "<", ">=", "<="] = ">"
    date_part = date_str

    if date_str.startswith(">="):
        operator = ">="
        date_part = date_str[2:]
    elif date_str.startswith("<="):
        operator = "<="
        date_part = date_str[2:]
    elif date_str.startswith(">"):
        operator = ">"
        date_part = date_str[1:]
    elif date_str.startswith("<"):
        operator = "<"
        date_part = date_str[1:]

    try:
        parsed_date = date_parser.parse(date_part)
        # Ensure datetime is timezone-aware
        if parsed_date.tzinfo is None:
            from datetime import timezone

            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        return (operator, parsed_date)
    except (ValueError, TypeError):
        return None


def format_single_result(
    content: ProcessedContent,
    return_type: str,
) -> str:
    """
    Format a single ProcessedContent result based on return type.

    Args:
        content: The ProcessedContent object
        return_type: The requested return type (st, u, c, m, t, d, s, id, json)

    Returns:
        Formatted string output
    """
    match return_type:
        case "st":
            return content.source_type
        case "u":
            return content.source.original_source
        case "c":
            return content.text
        case "m":
            return json.dumps(content.metadata, indent=2)
        case "t":
            return content.title
        case "d":
            return content.description
        case "s":
            return content.summary
        case "id":
            return content.uri
        case "json":
            return content.model_dump_json(indent=2)
        case _:
            return content.summary  # Default fallback


def output_data(printer: Printer, data: str) -> None:
    """
    Output data appropriately based on printer mode.

    In TTY mode, uses print_markdown for nice formatting.
    In piped mode, uses print_raw for clean data streams.

    Args:
        printer: The Printer instance
        data: The data to output
    """
    if printer.emit_data:
        # Piped mode - emit raw data
        printer.print_raw(data)
    else:
        # TTY mode - emit pretty output
        printer.print_markdown(data, add_rule=False)


def save_query_history(
    query_string: str,
    source_type: str | None,
    extension: str | None,
    results: list[ProcessedContent],
) -> None:
    """
    Save query execution to history database.

    Args:
        query_string: The search query
        source_type: Source type filter
        extension: Extension filter
        results: List of ProcessedContent results
    """
    if not results:
        return  # Don't save empty queries

    # Convert results to QueryResultItem format
    result_items = [
        QueryResultItem(
            uri=r.uri,
            title=r.title,
            source_type=r.source_type,
            created_at=r.created_at,
        )
        for r in results
    ]

    # Create QueryHistory object
    query_history = QueryHistory(
        query_string=query_string,
        source_type=source_type,
        extension=extension,
        executed_at=int(time.time()),
        results=result_items,
    )

    # Save to database
    repository = QueryHistoryRepository()
    repository.save(query_history)


def create_results_table(results: list[ProcessedContent]) -> Table:
    """
    Create a Rich table from search results with numbered rows.

    Args:
        results: List of ProcessedContent objects

    Returns:
        Rich Table object
    """
    table = Table(title="Search Results", show_header=True, header_style="bold magenta")
    table.add_column("#", style="bold blue", width=4)
    table.add_column("Title", style="cyan", width=40)
    table.add_column("Type", style="green", width=10)
    table.add_column("Date", style="yellow", width=20)

    for index, result in enumerate(results, start=1):
        # Format date
        date_obj = datetime.fromtimestamp(result.created_at)
        date_str = date_obj.strftime("%Y-%m-%d %H:%M")

        # Truncate title if too long
        title = result.title[:37] + "..." if len(result.title) > 40 else result.title

        table.add_row(str(index), title, result.source_type, date_str)

    return table


@click.command()
@click.argument("query_string", required=False, default="")
@click.option(
    "--type",
    "-t",
    "source_type",
    type=click.Choice(["youtube", "doc", "audio", "web", "drive"], case_sensitive=False),
    help="Filter by source type",
)
@click.option(
    "--limit",
    "-n",
    default=10,
    type=int,
    help="Maximum number of results to return",
)
@click.option(
    "--latest",
    "-l",
    is_flag=True,
    help="Get only the most recent item",
)
@click.option(
    "--history",
    is_flag=True,
    help="Show all items sorted by date (ignores query string)",
)
@click.option(
    "--date",
    "-d",
    help="Date filter (e.g., '>2024-01-01', '<2024-12-31')",
)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["sql", "semantic", "fuzzy"], case_sensitive=False),
    default="sql",
    help="Search mode: sql (default), semantic, or fuzzy",
)
@click.option(
    "--expand",
    is_flag=True,
    help="Expand top result to find related content (requires semantic search)",
)
@click.option(
    "--extension",
    "-e",
    help="Filter by file extension for document sources (e.g., pdf, docx, xlsx)",
)
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(["st", "u", "c", "m", "t", "d", "s", "id", "json"], case_sensitive=False),
    default="t",
    help="Output format: [st] source type, [u] url, [c] content, [m] metadata, [t] title (default), [d] description, [s] summary, [id] uri, json",
)
@click.option(
    "--open",
    "-o",
    is_flag=True,
    help="Open the source URL in a browser",
)
@click.option(
    "--raw",
    is_flag=True,
    help="Force raw output mode (no pretty formatting)",
)
@click.option(
    "--get",
    "-g",
    type=int,
    help="Retrieve item by number from previous query results",
)
def query(
    query_string: str,
    source_type: str | None,
    limit: int,
    latest: bool,
    history: bool,
    date: str | None,
    mode: str,
    expand: bool,
    extension: str | None,
    return_type: str,
    open: bool,
    raw: bool,
    get: int | None,
) -> None:
    """
    Search and retrieve ingested content from Siphon.

    Examples:
        siphon query "AI Agents"
        siphon query --type youtube --limit 5
        siphon query --latest --return-type c
        siphon query --history --limit 20
        siphon query "machine learning" --date ">2024-01-01"
        siphon query --type doc --extension pdf
        siphon query --history -e .docx --limit 10
        siphon query --get 2 -r s  # Get item #2 from last query
    """
    printer = Printer(raw=raw)
    client = SiphonClient()
    scratchpad = Scratchpad()

    # Handle --get flag (retrieve by index from scratchpad)
    if get is not None:
        uri = scratchpad.get(get)
        if uri is None:
            loaded_uris = scratchpad.load()
            if not loaded_uris:
                printer.print_pretty("[red]Error:[/red] Scratchpad is empty. Run a query first.")
            else:
                printer.print_pretty(
                    f"[red]Error:[/red] Invalid index {get}. "
                    f"Valid range: 1-{len(loaded_uris)}"
                )
            raise click.Abort()

        result = client.get_by_uri(uri)
        if not result:
            printer.print_pretty(f"[red]Error:[/red] Content not found for URI: {uri}")
            raise click.Abort()

        # Handle --open flag
        if open:
            click.launch(result.source.original_source)
            printer.print_pretty(
                f"[green]Opened:[/green] {result.source.original_source}"
            )
            return

        # Output based on return type
        output = format_single_result(result, return_type)
        output_data(printer, output)
        return

    # Parse date filter
    date_filter = parse_date_filter(date) if date else None
    if date and not date_filter:
        printer.print_pretty(f"[red]Error:[/red] Invalid date format: {date}")
        raise click.Abort()

    # Map CLI source type to enum
    source_type_enum = SOURCE_TYPE_MAP.get(source_type.lower()) if source_type else None

    # Normalize extension
    normalized_extension = normalize_extension(extension)

    try:
        # Determine which operation to perform
        if latest:
            # Get the latest single item
            result = client.get_latest()
            if not result:
                printer.print_pretty("[yellow]No content found.[/yellow]")
                return

            # Handle --open flag
            if open:
                click.launch(result.source.original_source)
                printer.print_pretty(
                    f"[green]Opened:[/green] {result.source.original_source}"
                )
                return

            # Output based on return type
            output = format_single_result(result, return_type)
            output_data(printer, output)

        elif history:
            # List all content sorted by date
            with printer.status("Fetching history..."):
                collection = client.list_all(
                    source_type=source_type_enum,
                    date_filter=date_filter,
                    limit=limit,
                    extension=normalized_extension,
                )

            results = collection.to_list()

            if not results:
                printer.print_pretty("[yellow]No results found.[/yellow]")
                return

            # Save to query history and update scratchpad
            if len(results) > 1:
                scratchpad.save_from_results(results)
                save_query_history(
                    query_string=query_string if not history else "",
                    source_type=source_type,
                    extension=normalized_extension,
                    results=results,
                )

            # If single result or pipe mode, output raw data
            if len(results) == 1 or printer.emit_data:
                for result in results:
                    output = format_single_result(result, return_type)
                    output_data(printer, output)
            else:
                # Pretty table for TTY mode
                table = create_results_table(results)
                printer.print_pretty(table)

        else:
            # Perform search
            with printer.status("Searching..."):
                collection = client.search(
                    query=query_string,
                    mode=mode,  # type: ignore[arg-type]
                    source_type=source_type_enum,
                    date_filter=date_filter,
                    limit=limit,
                    extension=normalized_extension,
                )

            # Handle --expand flag
            if expand:
                if not collection.to_list():
                    printer.print_pretty("[yellow]No results to expand.[/yellow]")
                    return
                try:
                    collection = collection.expand(query_string)
                except NotImplementedError as e:
                    printer.print_pretty(f"[red]Error:[/red] {e}")
                    raise click.Abort()

            results = collection.to_list()

            if not results:
                printer.print_pretty("[yellow]No results found.[/yellow]")
                return

            # Save to query history and update scratchpad
            if len(results) > 1:
                scratchpad.save_from_results(results)
                save_query_history(
                    query_string=query_string if not history else "",
                    source_type=source_type,
                    extension=normalized_extension,
                    results=results,
                )

            # Handle --open flag (opens first result)
            if open:
                first_result = results[0]
                click.launch(first_result.source.original_source)
                printer.print_pretty(
                    f"[green]Opened:[/green] {first_result.source.original_source}"
                )
                return

            # Output results
            if len(results) == 1 or printer.emit_data:
                for result in results:
                    output = format_single_result(result, return_type)
                    output_data(printer, output)
            else:
                # Pretty table for TTY mode
                table = create_results_table(results)
                printer.print_pretty(table)

    except NotImplementedError as e:
        printer.print_pretty(f"[red]Error:[/red] {e}")
        raise click.Abort()
    except Exception as e:
        printer.print_pretty(f"[red]Error:[/red] {e}")
        raise
