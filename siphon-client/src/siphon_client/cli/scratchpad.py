"""
Scratchpad module for persisting query results between commands.

The scratchpad stores URIs of recently queried ProcessedContent objects,
allowing users to retrieve specific items by their numbered position.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from siphon_api.models import ProcessedContent


def get_scratchpad_path() -> Path:
    """
    Get the path to the scratchpad file.

    Returns:
        Path to the scratchpad JSON file in the user's cache directory
    """
    cache_dir = Path.home() / ".cache" / "siphon"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "scratchpad.json"


class Scratchpad:
    """
    Manages persistent storage of query results.

    The scratchpad stores URIs from query results, allowing users to
    reference and retrieve items by their numbered position (1-indexed).
    """

    def __init__(self) -> None:
        """Initialize the Scratchpad."""
        self.path = get_scratchpad_path()

    def save(self, uris: list[str]) -> None:
        """
        Save URIs to the scratchpad.

        Args:
            uris: List of content URIs to save
        """
        data = {"results": uris}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def save_from_results(self, results: list[ProcessedContent]) -> None:
        """
        Save URIs extracted from ProcessedContent objects.

        Args:
            results: List of ProcessedContent objects
        """
        uris = [result.uri for result in results]
        self.save(uris)

    def load(self) -> list[str]:
        """
        Load URIs from the scratchpad.

        Returns:
            List of URIs, or empty list if scratchpad doesn't exist
        """
        if not self.path.exists():
            return []

        try:
            with open(self.path) as f:
                data = json.load(f)
            return data.get("results", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def get(self, index: int) -> str | None:
        """
        Get URI by 1-indexed position.

        Args:
            index: The 1-indexed position (1, 2, 3, ...)

        Returns:
            URI at that position, or None if index is invalid
        """
        uris = self.load()

        # Convert to 0-indexed and check bounds
        if index < 1 or index > len(uris):
            return None

        return uris[index - 1]
