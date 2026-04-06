from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any


class ExtractionMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_latency_ms": 0.0, "error_count": 0}
        )

    def record(self, extractor_name: str, latency_ms: float, error: bool) -> None:
        with self._lock:
            d = self._data[extractor_name]
            d["count"] += 1
            d["total_latency_ms"] += latency_ms
            if error:
                d["error_count"] += 1

    def get(self, extractor_name: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._data[extractor_name])

    def reset(self) -> None:
        with self._lock:
            self._data.clear()


extraction_metrics = ExtractionMetrics()
