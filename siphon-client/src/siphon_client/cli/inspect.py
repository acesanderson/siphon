"""Siphon inspect command — show the most recent enrichment_runs row for a URI.

Pure Postgres read. Dev tool for diffing prompt revisions, debugging weird
summaries, or handing a forensic payload to an LLM for "why did this happen?"
analysis.

Two output modes:
- Default: rich pretty-print for humans.
- --json: machine-readable dump suitable for piping into another tool or
  feeding to an LLM as context.
"""
from __future__ import annotations

import json as json_module
import sys
from datetime import datetime
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    pass


@click.command(name="inspect")
@click.argument("uri")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit raw JSON instead of a human-readable table.",
)
def inspect(uri: str, json_output: bool) -> None:
    """Show the most recent enrichment run for URI.

    Looks up enrichment_runs by URI and prints routing decision, status,
    timing, and the full conduit trace.

    Two intended use cases:

    \b
    Dev loop while iterating on guidelines or routing config:
        siphon inspect "youtube:///abc123XYZ"
        # See which tier and model ran. Diff against earlier runs to
        # confirm a prompt change is doing what you think.

    \b
    Forensic mode when a summary looks wrong:
        siphon inspect "youtube:///abc123XYZ" --json | jq .
        # Pipe the JSON trace (rendered prompts + redacted inputs) to
        # an LLM and ask "why is this output bad?"

    The first form pretty-prints a summary panel + a trace step table.
    The --json form emits the full trace_json (including rendered
    prompts and the redacted input echo). Pure Postgres read; no LLM
    call, no headwater hop.
    """
    from siphon_server.database.postgres.repository import REPOSITORY

    run = REPOSITORY.get_latest_enrichment_run(uri)
    if run is None:
        click.echo(
            f"No enrichment_runs row for uri={uri!r}. "
            "Either it was never enriched, or it was enriched before "
            "observability landed.",
            err=True,
        )
        sys.exit(1)

    if json_output:
        click.echo(json_module.dumps(run, indent=2, default=str))
        return

    _pretty_print(run)


def _pretty_print(run: dict) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    enriched_at = run.get("enriched_at")
    when = (
        datetime.fromtimestamp(enriched_at).strftime("%Y-%m-%d %H:%M:%S")
        if enriched_at
        else "unknown"
    )

    status = run.get("status", "?")
    status_style = "green" if status == "success" else "red"

    summary_table = Table.grid(padding=(0, 2))
    summary_table.add_row("[bold]URI[/bold]", run.get("uri", ""))
    summary_table.add_row("[bold]Enriched at[/bold]", when)
    summary_table.add_row(
        "[bold]Status[/bold]", f"[{status_style}]{status}[/{status_style}]"
    )
    if run.get("error_message"):
        summary_table.add_row(
            "[bold]Error[/bold]", f"[red]{run['error_message']}[/red]"
        )
    summary_table.add_row("[bold]Tier[/bold]", str(run.get("tier", "?")))
    summary_table.add_row("[bold]Strategy[/bold]", str(run.get("strategy", "?")))
    summary_table.add_row("[bold]Model[/bold]", str(run.get("model", "?")))
    summary_table.add_row("[bold]Host[/bold]", str(run.get("host", "?")))
    summary_table.add_row("[bold]Token count[/bold]", str(run.get("token_count", "?")))
    duration = run.get("duration_seconds")
    summary_table.add_row(
        "[bold]Duration[/bold]",
        f"{duration:.2f}s" if isinstance(duration, (int, float)) else "?",
    )
    summary_table.add_row(
        "[bold]Guideline hash[/bold]", str(run.get("guideline_hash", "?"))
    )

    console.print(Panel(summary_table, title="Enrichment Run", border_style="cyan"))

    trace = run.get("trace_json") or []
    if not trace:
        console.print("[dim]No trace entries.[/dim]")
        return

    trace_table = Table(
        title="Trace",
        show_header=True,
        header_style="bold magenta",
        show_lines=False,
    )
    trace_table.add_column("Step")
    trace_table.add_column("Status")
    trace_table.add_column("Duration (s)", justify="right")
    trace_table.add_column("Metadata keys", overflow="fold")

    for entry in trace:
        step = entry.get("step", "?")
        st = entry.get("status", "?")
        st_style = "green" if st == "success" else "red"
        dur = entry.get("duration")
        dur_str = f"{dur:.3f}" if isinstance(dur, (int, float)) else "?"
        meta_keys = ", ".join(sorted((entry.get("metadata") or {}).keys()))
        trace_table.add_row(step, f"[{st_style}]{st}[/{st_style}]", dur_str, meta_keys)

    console.print(trace_table)
    console.print(
        "[dim]Use --json for full trace including rendered prompts and "
        "redacted inputs.[/dim]"
    )
