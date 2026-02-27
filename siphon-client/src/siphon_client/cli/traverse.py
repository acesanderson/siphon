"""
Siphon traverse command - walk the wikilink graph from a known node.

Supports forward traversal (follow links outward) and reverse traversal
(find all nodes that link here). Designed to be source-type-agnostic;
Obsidian is the first implementation.
"""
from __future__ import annotations

from typing import Literal

import click

from siphon_client.cli.printer import Printer
from siphon_client.cli.query import create_results_table
from siphon_client.cli.query import format_single_result
from siphon_client.cli.query import output_data
from siphon_client.cli.scratchpad import Scratchpad
from siphon_client.client import SiphonClient


def _resolve_uri(node: str) -> str:
    """Accept either a bare note name or a full URI."""
    if ":///" in node:
        return node
    return f"obsidian:///{node}"


@click.command()
@click.argument("node")
@click.option(
    "--depth",
    "-d",
    default=1,
    type=int,
    show_default=True,
    help="Traversal depth (0 = root only, 1 = root + direct links, ...)",
)
@click.option(
    "--backlinks",
    "-b",
    is_flag=True,
    help="Reverse traversal: find all nodes that link TO this one",
)
@click.option(
    "--return-type",
    "-r",
    type=click.Choice(
        ["st", "u", "c", "m", "t", "d", "s", "id", "json"], case_sensitive=False
    ),
    default="t",
    help="Output format: [st] source type, [u] url, [c] content, [m] metadata, "
         "[t] title (default), [d] description, [s] summary, [id] uri, [json] full json",
)
@click.option(
    "--raw",
    is_flag=True,
    help="Force raw output mode (no pretty formatting)",
)
def traverse(
    node: str,
    depth: int,
    backlinks: bool,
    return_type: str,
    raw: bool,
) -> None:
    """
    Walk the wikilink graph from a node.

    NODE is a note name or full URI. Bare names are resolved as Obsidian notes.

    Examples:
        siphon traverse "My Note"
        siphon traverse "My Note" --depth 2
        siphon traverse "My Note" --backlinks
        siphon traverse obsidian:///My\\ Note --depth 3
    """
    printer = Printer(raw=raw)
    client = SiphonClient()
    scratchpad = Scratchpad()

    uri = _resolve_uri(node)

    direction = "backlinks for" if backlinks else f"depth-{depth} traversal from"
    with printer.status(f"Traversing ({direction} {uri})..."):
        collection = client.traverse(uri=uri, depth=depth, backlinks=backlinks)

    results = collection.to_list()

    if not results:
        if backlinks:
            printer.print_pretty(f"[yellow]No nodes link to {uri}.[/yellow]")
        else:
            printer.print_pretty(f"[yellow]No content found at {uri}.[/yellow]")
        return

    if len(results) > 1:
        scratchpad.save_from_results(results)

    if len(results) == 1 or printer.emit_data:
        for result in results:
            output = format_single_result(result, return_type)
            output_data(printer, output)
    else:
        table = create_results_table(results)
        printer.print_pretty(table)
