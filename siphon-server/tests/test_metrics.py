from __future__ import annotations


def test_metrics_record_latency_on_successful_extract():
    from siphon_server.metrics import extraction_metrics
    extraction_metrics.reset()
    extraction_metrics.record("doc", latency_ms=250.0, error=False)
    assert extraction_metrics.get("doc")["count"] == 1
    assert extraction_metrics.get("doc")["total_latency_ms"] == 250.0
    assert extraction_metrics.get("doc")["error_count"] == 0


def test_metrics_record_error_on_failed_extract():
    from siphon_server.metrics import extraction_metrics
    extraction_metrics.reset()
    extraction_metrics.record("doc", latency_ms=50.0, error=True)
    assert extraction_metrics.get("doc")["error_count"] == 1


def test_metrics_accumulate_across_calls():
    from siphon_server.metrics import extraction_metrics
    extraction_metrics.reset()
    extraction_metrics.record("doc", latency_ms=100.0, error=False)
    extraction_metrics.record("doc", latency_ms=200.0, error=False)
    assert extraction_metrics.get("doc")["count"] == 2
    assert extraction_metrics.get("doc")["total_latency_ms"] == 300.0
