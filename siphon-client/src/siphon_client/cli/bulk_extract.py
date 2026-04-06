from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from collections.abc import Sequence


def collect_sources(
    file: str | None,
    sources: Sequence[str],
    stdin_text: str | None,
) -> list[str]:
    """Priority: --file > inline args > stdin."""
    if file is not None:
        lines = Path(file).read_text(encoding="utf-8").splitlines()
        result = [l.strip() for l in lines if l.strip()]
    elif sources:
        result = list(sources)
    elif stdin_text:
        result = [l.strip() for l in stdin_text.splitlines() if l.strip()]
    else:
        result = []

    if not result:
        raise ValueError("No sources provided via --file, arguments, or stdin.")
    return result


@click.command("bulk-extract")
@click.argument("sources", nargs=-1)
@click.option("--file", "-f", default=None, help="Newline-delimited file of paths/URIs.")
@click.option("--max-concurrent", "-n", default=10, show_default=True)
@click.option("--output-dir", "-o", default=None, help="Write {slug}.txt files here.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output JSON array.")
def bulk_extract(
    sources: tuple[str, ...],
    file: str | None,
    max_concurrent: int,
    output_dir: str | None,
    output_json: bool,
) -> None:
    """Batch-extract raw text from multiple sources via headwater."""
    stdin_text = None if sys.stdin.isatty() else sys.stdin.read()
    try:
        source_list = collect_sources(file=file, sources=sources, stdin_text=stdin_text)
    except ValueError as e:
        raise click.UsageError(str(e))

    asyncio.run(_run(source_list, max_concurrent, output_dir, output_json))


async def _run(
    sources: list[str],
    max_concurrent: int,
    output_dir: str | None,
    output_json: bool,
) -> None:
    from siphon_api.api.batch_extract import BatchExtractRequest
    from siphon_server.services.batch_extract_service import batch_extract_siphon_service

    req = BatchExtractRequest(sources=sources, max_concurrent=max_concurrent)
    resp = await batch_extract_siphon_service(req)
    _emit_output(resp, output_dir, output_json)


def _emit_output(resp, output_dir: str | None, output_json: bool) -> None:
    from siphon_api.api.batch_extract import BatchExtractResponse
    assert isinstance(resp, BatchExtractResponse)

    if output_json:
        print(json.dumps([r.model_dump() for r in resp.results], indent=2))
        return

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        seen: dict[str, int] = {}
        for r in resp.results:
            if r.text is None:
                continue
            base_slug = _slugify(Path(r.source).stem)
            count = seen.get(base_slug, 0) + 1
            seen[base_slug] = count
            slug = base_slug if count == 1 else f"{base_slug}-{count}"
            if count > 1:
                click.echo(f"Warning: slug collision for '{base_slug}', writing as '{slug}.txt'", err=True)
            (out / f"{slug}.txt").write_text(r.text, encoding="utf-8")
        return

    for r in resp.results:
        status = "OK" if r.text else f"ERROR: {r.error}"
        print(f"{r.source}: {status}")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-").replace("_", "-"))
