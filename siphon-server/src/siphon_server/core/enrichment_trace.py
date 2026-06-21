"""Trace capture for enrichment runs.

Wraps a `SiphonPipeline.process()` enrichment call to capture conduit's @step
trace, redact bulky input echoes, classify outcomes, and persist a row to
`enrichment_runs` regardless of success or failure.

Two integration points:
- Orchestrator: `async with capture_enrichment(uri=source_info.uri):` around
  `self.enricher.execute(...)`.
- Enricher: `register_guideline(rendered_guideline)` after rendering the
  summary guideline. This propagates `guideline_hash` to the persisted row
  without changing the EnricherStrategy protocol.

Trace contents preserved verbatim: metadata (including rendered_prompt and
output text). Redacted: `inputs.input.data` truncated to 2KB; the
RoutingSummarizer `inputs.config.routing` collapsed to its profile names
since the full PRODUCTION_ROUTING list is held in code, not data.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from conduit.core.workflow.context import context as conduit_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_MAX_INPUT_TEXT_BYTES = 2048

_enrichment_state: ContextVar[dict | None] = ContextVar(
    "_enrichment_state", default=None
)


def register_guideline(rendered_guideline: str) -> None:
    """Called by an enricher to report the summary guideline it rendered.

    No-op when called outside a `capture_enrichment` context.
    """
    state = _enrichment_state.get()
    if state is None:
        return
    state["guideline_hash"] = hashlib.sha256(
        rendered_guideline.encode("utf-8")
    ).hexdigest()[:16]


@asynccontextmanager
async def capture_enrichment(*, uri: str) -> AsyncIterator[dict]:
    """Capture conduit trace + persist an enrichment_runs row on exit.

    Always writes a row when at least one @step entry was captured. If the
    enricher raised, status is classified from the exception and the row is
    still written (then the exception re-raises).
    """
    trace_log: list[dict] = []
    state: dict[str, Any] = {
        "uri": uri,
        "guideline_hash": None,
        "exception": None,
    }
    token_trace = conduit_context.trace.set(trace_log)
    token_state = _enrichment_state.set(state)
    started_at = time.time()
    try:
        yield state
    except Exception as e:
        state["exception"] = e
        raise
    finally:
        conduit_context.trace.reset(token_trace)
        _enrichment_state.reset(token_state)
        duration = time.time() - started_at
        if trace_log:
            try:
                _persist(
                    uri=uri,
                    guideline_hash=state.get("guideline_hash"),
                    exception=state.get("exception"),
                    trace_log=trace_log,
                    duration_seconds=duration,
                    enriched_at=int(started_at),
                )
            except Exception:
                logger.exception(
                    "Failed to persist enrichment_runs row for uri=%s", uri
                )


def _persist(
    *,
    uri: str,
    guideline_hash: str | None,
    exception: BaseException | None,
    trace_log: list[dict],
    duration_seconds: float,
    enriched_at: int,
) -> None:
    from siphon_server.database.postgres.repository import REPOSITORY

    routing = _find_step(trace_log, "RoutingSummarizer")
    routing_meta = routing.get("metadata", {}) if routing else {}
    tier = routing_meta.get("routed_profile", "unknown")
    strategy = routing_meta.get("routed_strategy", "unknown")
    token_count = int(routing_meta.get("token_count", 0))

    inner = _find_step(trace_log, strategy) if strategy != "unknown" else None
    inner_config = (
        inner.get("inputs", {}).get("config", {}) if inner else {}
    )
    model = str(inner_config.get("model", "unknown"))
    host = str(inner_config.get("host_alias", "unknown"))

    if exception is not None:
        status = _classify_exception(exception)
        error_message = str(exception)[:1000]
    else:
        outer_output = trace_log[-1].get("output") if trace_log else None
        if isinstance(outer_output, str) and not outer_output.strip():
            status = "empty_output"
            error_message = None
        else:
            status = "success"
            error_message = None

    redacted = [_redact_entry(e) for e in trace_log]

    REPOSITORY.insert_enrichment_run(
        uri=uri,
        enriched_at=enriched_at,
        tier=tier,
        strategy=strategy,
        token_count=token_count,
        model=model,
        host=host,
        status=status,
        error_message=error_message,
        duration_seconds=round(duration_seconds, 4),
        guideline_hash=guideline_hash or "unknown",
        trace_json=redacted,
    )


def _classify_exception(exc: BaseException) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    return "model_error"


def _find_step(trace_log: list[dict], strategy_name: str) -> dict | None:
    for entry in trace_log:
        step = entry.get("step", "")
        if strategy_name in step:
            return entry
    return None


def _redact_entry(entry: dict) -> dict:
    out = dict(entry)
    inputs = out.get("inputs")
    if isinstance(inputs, dict):
        out["inputs"] = _redact_inputs(inputs)
    out["output"] = _safe(out.get("output"))
    out["metadata"] = _safe(out.get("metadata"))
    return out


def _redact_inputs(inputs: dict) -> dict:
    result: dict[str, Any] = {}
    for k, v in inputs.items():
        if k == "input":
            result[k] = _redact_text_input(v)
        elif k == "config":
            result[k] = _redact_config(v)
        else:
            result[k] = _safe(v)
    return result


def _redact_text_input(v: Any) -> Any:
    if not is_dataclass(v):
        return _safe(v)
    d = asdict(v)
    data = d.get("data")
    if isinstance(data, str):
        encoded = data.encode("utf-8")
        if len(encoded) > _MAX_INPUT_TEXT_BYTES:
            d["data"] = encoded[:_MAX_INPUT_TEXT_BYTES].decode(
                "utf-8", errors="ignore"
            )
            d["_data_truncated"] = True
            d["_data_full_length_bytes"] = len(encoded)
    return d


def _redact_config(config: Any) -> Any:
    if not isinstance(config, dict):
        return _safe(config)
    result: dict[str, Any] = {}
    for k, v in config.items():
        if k == "routing":
            try:
                result[k] = [
                    {
                        "max_tokens": int(max_t),
                        "profile_name": getattr(prof, "name", str(prof)),
                    }
                    for max_t, prof in v
                ]
            except Exception:
                result[k] = "<unserializable>"
        else:
            result[k] = _safe(v)
    return result


def _safe(v: Any) -> Any:
    from pydantic import BaseModel

    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _safe(val) for k, val in v.items()}
    if is_dataclass(v):
        return _safe(asdict(v))
    if isinstance(v, BaseModel):
        return _safe(v.model_dump())
    if isinstance(v, type):
        return v.__name__
    return str(v)
