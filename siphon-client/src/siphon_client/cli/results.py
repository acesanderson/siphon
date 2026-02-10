"""
Siphon results command - recall and manage query history.

Provides "arrow-up" style query recall, listing recent queries,
and loading specific query results by ID.
"""
from __future__ import annotations

import click
from datetime import datetime
from rich.table import Table

from siphon_client.cli.printer import Printer
from siphon_server.database.postgres.repository import QueryHistoryRepository


def format_time_ago(timestamp: int) -> str:
    """
    Format timestamp as relative time (e.g., '2 hours ago').

    Args:
        timestamp: Unix timestamp

    Returns:
        Human-readable relative time string
    """
    now = datetime.now()
    then = datetime.fromtimestamp(timestamp)
    delta = now - then

    if delta.days > 0:
        if delta.days == 1:
            return "1 day ago"
        return f"{delta.days} days ago"

    hours = delta.seconds // 3600
    if hours > 0:
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"

    minutes = delta.seconds // 60
    if minutes > 0:
        if minutes == 1:
            return "1 minute ago"
        return f"{minutes} minutes ago"

    return "just now"


def format_query_description(
    query_string: str,
    source_type: str | None,
    extension: str | None,
) -> str:
    """
    Format query parameters as human-readable description.

    Args:
        query_string: The search query
        source_type: Source type filter
        extension: Extension filter

    Returns:
        Formatted query description
    """
    if not query_string:
        desc = "[all history]"
    else:
        desc = f'"{query_string}"'

    filters = []
    if source_type:
        filters.append(f"type: {source_type}")
    if extension:
        filters.append(f"ext: {extension}")

    if filters:
        desc += f" ({', '.join(filters)})"

    return desc


def create_history_table(queries: list) -> Table:
    """
    Create a Rich table for query history.

    Args:
        queries: List of QueryHistory objects

    Returns:
        Rich Table object
    """
    table = Table(title="Query History", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="bold blue", width=6)
    table.add_column("Query", style="cyan", width=40)
    table.add_column("Results", style="green", width=10)
    table.add_column("When", style="yellow", width=20)

    for query in queries:
        query_desc = format_query_description(
            query.query_string,
            query.source_type,
            query.extension,
        )

        # Truncate long queries
        if len(query_desc) > 37:
            query_desc = query_desc[:34] + "..."

        table.add_row(
            str(query.id),
            query_desc,
            str(query.result_count),
            format_time_ago(query.executed_at),
        )

    return table


@click.command()
@click.option(
    "--history",
    is_flag=True,
    help="List recent query history",
)
@click.option(
    "--get",
    "-g",
    type=int,
    help="Load results from specific query by ID",
)
@click.option(
    "--limit",
    "-n",
    default=20,
    type=int,
    help="Maximum number of history entries to show",
)
@click.option(
    "--raw",
    is_flag=True,
    help="Force raw output mode (no pretty formatting)",
)
def results(
    history: bool,
    get: int | None,
    limit: int,
    raw: bool,
) -> None:
    """
    Recall and manage query history (like terminal arrow-up).

    Examples:
        siphon results              # Show last query results
        siphon results --history    # List all recent queries
        siphon results --get 3      # Load results from query #3
    """
    printer = Printer(raw=raw)
    repository = QueryHistoryRepository()

    if history:
        # List recent query history
        with printer.status("Loading query history..."):
            queries = repository.list_recent(limit=limit)

        if not queries:
            printer.print_pretty("[yellow]No query history found.[/yellow]")
            return

        # Display history table
        table = create_history_table(queries)
        printer.print_pretty(table)
        printer.print_pretty("\n[dim]Use: siphon results --get <ID> to load that query's results[/dim]")

    elif get is not None:
        # Load specific query by ID
        query_hist = repository.get_by_id(get)

        if not query_hist:
            printer.print_pretty(f"[red]Error:[/red] Query #{get} not found in history.")
            raise click.Abort()

        if not query_hist.results:
            printer.print_pretty(f"[yellow]Query #{get} has no results.[/yellow]")
            return

        # Import here to avoid circular dependency
        from siphon_client.cli.query import create_results_table

        # Display results table
        # Convert QueryResultItem to format expected by create_results_table
        # This is a bit hacky - we're creating mock ProcessedContent-like objects
        from siphon_api.models import ProcessedContent, SourceInfo, ContentData, EnrichedData
        from siphon_api.enums import SourceType

        results = []
        for item in query_hist.results:
            # Create minimal ProcessedContent for table display
            pc = ProcessedContent(
                source=SourceInfo(
                    source_type=SourceType(item.source_type),
                    uri=item.uri,
                    original_source="",  # Not needed for table
                ),
                content=ContentData(
                    source_type=SourceType(item.source_type),
                    text="",  # Not needed for table
                    metadata={},
                ),
                enrichment=EnrichedData(
                    source_type=SourceType(item.source_type),
                    title=item.title,
                    description="",
                    summary="",
                ),
                created_at=item.created_at,
                updated_at=item.created_at,
            )
            results.append(pc)

        table = create_results_table(results)

        # Add query description as caption
        query_desc = format_query_description(
            query_hist.query_string,
            query_hist.source_type,
            query_hist.extension,
        )
        table.caption = f"Results for: {query_desc} (Query #{get})"

        printer.print_pretty(table)
        printer.print_pretty("\n[dim]Use: siphon query --get <#> to retrieve individual items[/dim]")

    else:
        # Show latest query results (default behavior)
        query_hist = repository.get_latest()

        if not query_hist:
            printer.print_pretty("[yellow]No query history found. Run a query first.[/yellow]")
            return

        if not query_hist.results:
            printer.print_pretty("[yellow]Last query has no results.[/yellow]")
            return

        # Same table display logic as above
        from siphon_client.cli.query import create_results_table
        from siphon_api.models import ProcessedContent, SourceInfo, ContentData, EnrichedData
        from siphon_api.enums import SourceType

        results = []
        for item in query_hist.results:
            pc = ProcessedContent(
                source=SourceInfo(
                    source_type=SourceType(item.source_type),
                    uri=item.uri,
                    original_source="",
                ),
                content=ContentData(
                    source_type=SourceType(item.source_type),
                    text="",
                    metadata={},
                ),
                enrichment=EnrichedData(
                    source_type=SourceType(item.source_type),
                    title=item.title,
                    description="",
                    summary="",
                ),
                created_at=item.created_at,
                updated_at=item.created_at,
            )
            results.append(pc)

        table = create_results_table(results)

        query_desc = format_query_description(
            query_hist.query_string,
            query_hist.source_type,
            query_hist.extension,
        )
        table.caption = f"Results for: {query_desc}"

        printer.print_pretty(table)
        printer.print_pretty("\n[dim]Use: siphon query --get <#> to retrieve individual items[/dim]")
