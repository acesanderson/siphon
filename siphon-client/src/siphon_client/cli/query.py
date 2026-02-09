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
from siphon_api.models import ProcessedContent
from siphon_client.cli.printer import Printer
from siphon_client.client import SiphonClient
from siphon_client.collections.collection import Collection


# Mapping of CLI source type names to SourceType enum
SOURCE_TYPE_MAP = {
    "youtube": SourceType.YOUTUBE,
    "doc": SourceType.DOC,
    "audio": SourceType.AUDIO,
    "web": SourceType.ARTICLE,  # Note: "web" maps to ARTICLE
    "drive": SourceType.DRIVE,
}


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


def create_results_table(results: list[ProcessedContent]) -> Table:
    """
    Create a Rich table from search results.

    Args:
        results: List of ProcessedContent objects

    Returns:
        Rich Table object
    """
    table = Table(title="Search Results", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=20)
    table.add_column("Title", style="cyan", width=40)
    table.add_column("Type", style="green", width=10)
    table.add_column("Date", style="yellow", width=20)

    for result in results:
        # Format date
        date_obj = datetime.fromtimestamp(result.created_at)
        date_str = date_obj.strftime("%Y-%m-%d %H:%M")

        # Truncate title if too long
        title = result.title[:37] + "..." if len(result.title) > 40 else result.title

        # Extract a short ID from URI
        uri_parts = result.uri.split("/")
        short_id = uri_parts[-1] if uri_parts else result.uri[:20]

        table.add_row(short_id, title, result.source_type, date_str)

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
    "-e",
    is_flag=True,
    help="Expand top result to find related content (requires semantic search)",
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
def query(
    query_string: str,
    source_type: str | None,
    limit: int,
    latest: bool,
    history: bool,
    date: str | None,
    mode: str,
    expand: bool,
    return_type: str,
    open: bool,
    raw: bool,
) -> None:
    """
    Search and retrieve ingested content from Siphon.

    Examples:
        siphon query "AI Agents"
        siphon query --type youtube --limit 5
        siphon query --latest --return-type c
        siphon query --history --limit 20
        siphon query "machine learning" --date ">2024-01-01"
    """
    printer = Printer(raw=raw)
    client = SiphonClient()

    # Parse date filter
    date_filter = parse_date_filter(date) if date else None
    if date and not date_filter:
        printer.print_pretty(f"[red]Error:[/red] Invalid date format: {date}")
        raise click.Abort()

    # Map CLI source type to enum
    source_type_enum = SOURCE_TYPE_MAP.get(source_type.lower()) if source_type else None

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
                )

            results = collection.to_list()

            if not results:
                printer.print_pretty("[yellow]No results found.[/yellow]")
                return

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
