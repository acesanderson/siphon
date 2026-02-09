"""Tests for the query command."""
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


def test_query_with_text_search_calls_client_search(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query command should call client.search with query string."""
    mock_collection = Collection([sample_content], mock_client)
    mock_client.search.return_value = mock_collection

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["test query", "--limit", "10"])

    assert result.exit_code == 0
    mock_client.search.assert_called_once()


def test_query_with_latest_flag_calls_client_get_latest(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query command with --latest should call client.get_latest."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest"])

    assert result.exit_code == 0
    mock_client.get_latest.assert_called_once()


def test_query_with_history_flag_calls_client_list_all(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query command with --history should call client.list_all."""
    mock_collection = Collection([sample_content], mock_client)
    mock_client.list_all.return_value = mock_collection

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--history", "--limit", "20"])

    assert result.exit_code == 0
    mock_client.list_all.assert_called_once()


def test_query_with_type_filter_passes_source_type(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query command with --type should filter by source type."""
    mock_collection = Collection([sample_content], mock_client)
    mock_client.search.return_value = mock_collection

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["test", "--type", "youtube"])

    assert result.exit_code == 0
    call_args = mock_client.search.call_args
    assert call_args.kwargs["source_type"] == SourceType.YOUTUBE


def test_query_return_type_content_outputs_text(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type c should output content text."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "c"])

    assert result.exit_code == 0
    assert "This is the full content text" in result.output


def test_query_return_type_title_outputs_title(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type t should output title."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "t"])

    assert result.exit_code == 0
    assert "Test Video Title" in result.output


def test_query_return_type_summary_outputs_summary(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type s should output summary."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "s"])

    assert result.exit_code == 0
    assert "Brief summary" in result.output


def test_query_return_type_url_outputs_original_source(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type u should output original source URL."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "u"])

    assert result.exit_code == 0
    assert "https://youtube.com/watch?v=test123" in result.output


def test_query_return_type_id_outputs_uri(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type id should output URI."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "id"])

    assert result.exit_code == 0
    assert "youtube:///test123" in result.output


def test_query_return_type_source_type_outputs_source_type(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type st should output source type."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "st"])

    assert result.exit_code == 0
    assert "YouTube" in result.output


def test_query_return_type_metadata_outputs_metadata(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type m should output metadata as JSON."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "m"])

    assert result.exit_code == 0
    # metadata is empty dict in fixture, should output {}
    assert "{" in result.output


def test_query_return_type_description_outputs_description(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --return-type d should output description."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["--latest", "--return-type", "d"])

    assert result.exit_code == 0
    assert "Test video description" in result.output


def test_query_with_semantic_mode_shows_error(
    runner: CliRunner,
    mock_client: MagicMock,
) -> None:
    """query with --mode semantic should show NotImplementedError."""
    mock_client.search.side_effect = NotImplementedError("Semantic search")

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["test", "--mode", "semantic"])

    assert result.exit_code != 0
    assert "Semantic search" in result.output or "Error" in result.output


def test_query_with_open_flag_attempts_to_launch_url(
    runner: CliRunner,
    mock_client: MagicMock,
    sample_content: ProcessedContent,
) -> None:
    """query with --open should attempt to open URL in browser."""
    mock_client.get_latest.return_value = sample_content

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        with patch("click.launch") as mock_launch:
            result = runner.invoke(query, ["--latest", "--open"])

    assert result.exit_code == 0
    mock_launch.assert_called_once_with("https://youtube.com/watch?v=test123")


def test_query_no_results_shows_appropriate_message(
    runner: CliRunner,
    mock_client: MagicMock,
) -> None:
    """query with no results should show appropriate message."""
    mock_collection = Collection([], mock_client)
    mock_client.search.return_value = mock_collection

    with patch("siphon_client.cli.query.SiphonClient", return_value=mock_client):
        result = runner.invoke(query, ["nonexistent query"])

    assert result.exit_code == 0
    assert "No results" in result.output or result.output.strip() == ""
