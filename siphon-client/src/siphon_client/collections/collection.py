from __future__ import annotations

from typing import Callable, TypeVar, Generic, TYPE_CHECKING

from siphon_api.models import ProcessedContent

if TYPE_CHECKING:
    from siphon_client.client import SiphonClient

T = TypeVar("T")


class Collection(Generic[T]):
    """
    Monadic collection for chaining operations.
    Inspired by pandas, LINQ, and functional programming.
    """

    def __init__(self, items: list[T], client: SiphonClient) -> None:
        self._items = items
        self._client = client

    def map(self, fn: Callable[[T], T]) -> "Collection[T]":
        """Functor: transform each item"""
        return Collection([fn(item) for item in self._items], self._client)

    def flatmap(self, fn: Callable[[T], "Collection[T]"]) -> "Collection[T]":
        """Monad: transform and flatten"""
        result = []
        for item in self._items:
            result.extend(fn(item)._items)
        return Collection(result, self._client)

    def filter(self, predicate: Callable[[T], bool]) -> "Collection[T]":
        """Keep items matching predicate"""
        return Collection(
            [item for item in self._items if predicate(item)], self._client
        )

    def expand(self, query: str) -> Collection[ProcessedContent]:
        """
        Semantic expansion - find related content.
        This makes a server call for semantic search.
        """
        uris = [item.uri for item in self._items]  # type: ignore[attr-defined]
        related = self._client.find_related(uris, query)
        return Collection(related, self._client)

    def group_by(self, key: Callable[[T], str]) -> dict[str, "Collection[T]"]:
        """Group items by key function"""
        groups: dict[str, list[T]] = {}
        for item in self._items:
            k = key(item)
            if k not in groups:
                groups[k] = []
            groups[k].append(item)
        return {k: Collection(v, self._client) for k, v in groups.items()}

    # Terminal operations
    def to_list(self) -> list[T]:
        return self._items

    def count(self) -> int:
        return len(self._items)

    def first(self) -> T | None:
        return self._items[0] if self._items else None

    def take(self, n: int) -> "Collection[T]":
        return Collection(self._items[:n], self._client)
