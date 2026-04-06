from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner


def _mock_batch_response(sources: list[str], error_sources: list[str] | None = None):
    from siphon_api.api.batch_extract import BatchExtractResponse, BatchExtractResult
    error_sources = error_sources or []
    return BatchExtractResponse(results=[
        BatchExtractResult(
            source=s,
            text=None if s in error_sources else f"text of {s}",
            error="failed" if s in error_sources else None,
        )
        for s in sources
    ])


def test_collect_sources_from_inline_args():
    from siphon_client.cli.bulk_extract import collect_sources
    sources = collect_sources(file=None, sources=("a.pdf", "b.txt"), stdin_text=None)
    assert sources == ["a.pdf", "b.txt"]


def test_collect_sources_from_file(tmp_path):
    from siphon_client.cli.bulk_extract import collect_sources
    f = tmp_path / "sources.txt"
    f.write_text("a.pdf\nb.txt\n\n")
    sources = collect_sources(file=str(f), sources=(), stdin_text=None)
    assert sources == ["a.pdf", "b.txt"]


def test_collect_sources_file_takes_priority_over_args(tmp_path):
    from siphon_client.cli.bulk_extract import collect_sources
    f = tmp_path / "sources.txt"
    f.write_text("file_source.pdf\n")
    sources = collect_sources(file=str(f), sources=("arg_source.pdf",), stdin_text=None)
    assert sources == ["file_source.pdf"]


def test_collect_sources_from_stdin():
    from siphon_client.cli.bulk_extract import collect_sources
    sources = collect_sources(file=None, sources=(), stdin_text="a.pdf\nb.pdf\n")
    assert sources == ["a.pdf", "b.pdf"]


def test_collect_sources_empty_raises():
    from siphon_client.cli.bulk_extract import collect_sources
    with pytest.raises(ValueError, match="No sources"):
        collect_sources(file=None, sources=(), stdin_text=None)


def test_output_dir_writes_txt_files(tmp_path):
    from siphon_client.cli.bulk_extract import _emit_output
    from siphon_api.api.batch_extract import BatchExtractResponse, BatchExtractResult
    resp = BatchExtractResponse(results=[
        BatchExtractResult(source="/docs/my file.pdf", text="hello content", error=None),
        BatchExtractResult(source="/docs/other.txt", text="other text", error=None),
    ])
    _emit_output(resp, output_dir=str(tmp_path), output_json=False)
    assert (tmp_path / "my-file.txt").read_text() == "hello content"
    assert (tmp_path / "other.txt").read_text() == "other text"


def test_output_dir_skips_failed_items(tmp_path):
    from siphon_client.cli.bulk_extract import _emit_output
    from siphon_api.api.batch_extract import BatchExtractResponse, BatchExtractResult
    resp = BatchExtractResponse(results=[
        BatchExtractResult(source="bad.pdf", text=None, error="docling failed"),
    ])
    _emit_output(resp, output_dir=str(tmp_path), output_json=False)
    assert list(tmp_path.iterdir()) == []


def test_json_output_includes_all_results(capsys):
    from siphon_client.cli.bulk_extract import _emit_output
    from siphon_api.api.batch_extract import BatchExtractResponse, BatchExtractResult
    resp = BatchExtractResponse(results=[
        BatchExtractResult(source="a.pdf", text="text", error=None),
        BatchExtractResult(source="b.pdf", text=None, error="failed"),
    ])
    _emit_output(resp, output_dir=None, output_json=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 2
    assert data[1]["error"] == "failed"


def test_slug_collision_writes_deduplicated_names(tmp_path):
    """Two sources with the same stem produce {slug}.txt and {slug}-2.txt."""
    from siphon_client.cli.bulk_extract import _emit_output
    from siphon_api.api.batch_extract import BatchExtractResponse, BatchExtractResult
    resp = BatchExtractResponse(results=[
        BatchExtractResult(source="/a/report.pdf", text="first", error=None),
        BatchExtractResult(source="/b/report.pdf", text="second", error=None),
    ])
    _emit_output(resp, output_dir=str(tmp_path), output_json=False)
    assert (tmp_path / "report.txt").read_text() == "first"
    assert (tmp_path / "report-2.txt").read_text() == "second"


def test_bulk_extract_registered_as_siphon_subcommand():
    from siphon_client.cli.siphon_cli import siphon
    assert "bulk-extract" in siphon.commands
