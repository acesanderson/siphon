"""Tests for query command TTY output behavior."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from siphon_api.enums import SourceType
from siphon_api.models import (
    ContentData,
    EnrichedData,
    ProcessedContent,
    SourceInfo,
)
from siphon_client.cli.query import query
from siphon_client.collections.collection import Collection


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock SiphonClient."""
    return MagicMock()


@pytest.fixture
def sample_content() -> ProcessedContent:
    """Create sample ProcessedContent for testing."""
    return ProcessedContent(
        source=SourceInfo(
            source_type=SourceType.YOUTUBE,
            uri="youtube:///test123",
            original_source="https://youtube.com/watch?v=test123",
        ),
        content=ContentData(
            source_type=SourceType.YOUTUBE,
            text="This is the full content text",
            metadata={},
        ),
        enrichment=EnrichedData(
            source_type=SourceType.YOUTUBE,
            title="Test Video Title",
            description="Test video description with details",
            summary="Brief summary of the content",
        ),
        created_at=int(datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp()),
        updated_at=int(datetime(2024, 1, 15, tzinfo=timezone.utc).timestamp()),
    )


def test_query_latest_shows_output_in_tty_mode(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query --latest should show output in TTY mode (not just piped mode)."""
    mock_client.get_latest.return_value = sample_content

    # Simulate TTY mode by patching IS_TTY
    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("siphon_client.cli.printer.IS_TTY", True):
            result = runner.invoke(query, ["--latest"])

    assert result.exit_code == 0
    # Should show the title (default return type) in output
    assert "Test Video Title" in result.output
    assert result.output.strip() != ""


def test_query_latest_with_return_type_content_shows_in_tty(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query --latest -r c should show content in TTY mode."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("siphon_client.cli.printer.IS_TTY", True):
            result = runner.invoke(query, ["--latest", "-r", "c"])

    assert result.exit_code == 0
    assert "This is the full content text" in result.output


def test_query_latest_with_return_type_summary_shows_in_tty(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query --latest -r s should show summary in TTY mode."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("siphon_client.cli.printer.IS_TTY", True):
            result = runner.invoke(query, ["--latest", "-r", "s"])

    assert result.exit_code == 0
    assert "Brief summary" in result.output


def test_query_latest_with_return_type_description_shows_in_tty(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query --latest -r d should show description in TTY mode."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("siphon_client.cli.printer.IS_TTY", True):
            result = runner.invoke(query, ["--latest", "-r", "d"])

    assert result.exit_code == 0
    assert "Test video description" in result.output


def test_query_search_single_result_shows_in_tty(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with single search result should show output in TTY mode."""
    mock_collection = Collection([sample_content], mock_client)
    mock_client.search.return_value = mock_collection

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("siphon_client.cli.printer.IS_TTY", True):
            result = runner.invoke(query, ["test query", "-r", "t"])

    assert result.exit_code == 0
    assert "Test Video Title" in result.output


def test_query_history_single_result_shows_in_tty(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query --history with single result should show output in TTY mode."""
    mock_collection = Collection([sample_content], mock_client)
    mock_client.list_all.return_value = mock_collection

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("siphon_client.cli.printer.IS_TTY", True):
            result = runner.invoke(query, ["--history", "-r", "t"])

    assert result.exit_code == 0
    assert "Test Video Title" in result.output
