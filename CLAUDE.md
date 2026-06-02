# Siphon — Agent Development Guide

Siphon is a media processing pipeline (audio transcription, diarization, image generation) that runs on two Linux hosts. This file tells you how to develop, deploy, and debug it as a coding agent.

---

## Active Work — Enrichment + Retrieval Refactor

**Status as of 2026-06-01.**

A multi-session refactor is in progress to (a) delegate summarization to conduit's `RoutingSummarizer` so long-form content gets routed to the right strategy, and (b) reshape Siphon's description artifact into a HyDE-aligned, retrieval-only artifact backed by a better embedding model.

**Phase 3 of conduit-side work is shipped and deployed.**
- `ArticleEnricher` now delegates summarization to `conduit.RoutingSummarizer` with a per-source `guideline.jinja2` (commit `040cfe3`).
- All four headwater hosts are running the new code as of 2026-06-01.
- Article is the only source type migrated so far. 10 others still use the legacy "single-shot model.query against raw text" pattern.

**Pick up here tomorrow:**

1. **Read `siphon-server/dev/summarization.md`** — current enrichment architecture, article = template, migration recipe for the other 10 source types.
2. **Read `siphon-server/dev/retrieval.md`** — embedding migration plan (all-MiniLM-L6-v2 → nomic-embed-text-v2), description redesign as HyDE-shaped retrieval artifact, query-side HyDE + BM25 + RRF, five-phase rollout (R1–R5).
3. **Conduit-side context** — `$BC/conduit-project/evals/STRATEGY.md`. The "Published Routing Decision" section explains tier breakpoints, models, hosts. RoutingSummarizer + `PRODUCTION_ROUTING` is in conduit at `src/conduit/strategies/summarize/summarizers/routing.py`.

**Recommended next action: Phase R1 in `retrieval.md`** — redesign Article's description to be HyDE-shaped, generated as a one-shot pass on top of the summary (not raw text). Iterate the prompt against a real article. This unblocks Phase R2 (embedding migration).

**Open follow-ups not on the critical path:**
- Cronicle event `emothl43a01` (the conduit eval rerun) is timing out at the 4h Cronicle limit and writing 0-byte NAS logs. Worth fixing but doesn't block Siphon work.
- Other 10 enrichers wait for description redesign to settle before mass-migration.

---

## Host Map

| Host | Role | Headwater services |
|---|---|---|
| caruana | primary siphon-server host | `headwaterrouter` (8081), `bywater` (8080) |
| alphablue | GPU worker host (diarization, whisper, imagegen) | `deepwater` (8080) |

---

## The Inner Loop

**1. Make code changes locally.**

**2. Deploy:**
```bash
bash scripts/deploy.sh                          # push + pull on both hosts
bash scripts/deploy.sh caruana                  # caruana only
bash scripts/deploy.sh alphablue                # alphablue only
bash scripts/deploy.sh --restart-workers        # both hosts + rebuild Docker workers
bash scripts/deploy.sh --restart-workers alphablue  # alphablue only + rebuild workers
```

**What the script does:**
- Pushes local branch to GitHub
- SSH into each target host and runs `git pull --ff-only`
- Runs `uv sync` in `siphon-server/` on each host (always — deps are always synced)
- `--restart-workers`: additionally rebuilds and restarts Docker worker containers on alphablue, then polls each worker's `/health` endpoint until `status == "healthy"` (or exits non-zero on timeout/error)

**Headwater restart required for code changes:** headwater is a persistent process that imports siphon-server as a library. File changes on disk are not picked up until headwater restarts. After deploying siphon, restart headwater on the relevant host(s) using headwater's own deploy script:

```bash
# from $BC/headwater
bash scripts/deploy.sh caruana      # restarts headwaterrouter + bywater on caruana
bash scripts/deploy.sh alphablue    # restarts deepwater on alphablue
bash scripts/deploy.sh              # both hosts
```

The headwater deploy script pulls, optionally syncs deps (`--sync-deps`), restarts the systemd services, and waits for `/ping` to confirm they're up.

---

## Worker Ports (alphablue)

| Worker | Port |
|---|---|
| diarization_gpu | 8000 |
| whisper_gpu | 8002 |
| flux_imagegen | 8001 |

Workers run as Docker containers. The `hf_cache` volume is preserved across restarts to avoid re-downloading large models. Delete it manually only to bust a stale auth cache:
```bash
docker volume rm <project_name>_hf_cache
```

---

## Ground Rules for Claude

- **Never SSH directly.** All remote operations go through the approved deploy scripts (`scripts/deploy.sh` in this repo, `scripts/deploy.sh` in `$BC/headwater`).

## Ground Rules

- **Deploy before testing.** Local edits do nothing until `deploy.sh` runs.
- **`uv sync` always runs** — no separate flag needed for dependency changes.
- **Use `--restart-workers` only when worker code or Dockerfiles changed.** It rebuilds images and waits up to 300s per worker for health — it's slow.
- **After deploying siphon, restart headwater.** Headwater imports siphon as a library and caches it at startup — `uv sync` alone is not enough. Run `bash scripts/deploy.sh caruana` from `$BC/headwater` to restart the relevant services.
- **If a worker fails to come up**, the script prints the last 50 log lines and exits non-zero. Read logs before retrying.

---

## Project Layout

```
siphon/
  siphon-api/     shared Pydantic models
  siphon-client/  client library
  siphon-server/  FastAPI server + Docker worker sidecars
    src/siphon_server/workers/
      diarization_gpu/   Docker worker (:8000)
      whisper_gpu/       Docker worker (:8002)
      flux_imagegen/     Docker worker (:8001)
  scripts/deploy.sh
  docs/           feature specs and plans
```

---

## Non-Negotiable Behavioral Rules

### Local Models Only — DATA PRIVACY RULE

**Never fall back to cloud models when the user requests local inference.** Content processed here (meeting transcripts, licensing data, internal analysis) must not leave to Anthropic, OpenAI, Google, or any third-party cloud API.

If `gpt-oss:latest` via Headwater is unreachable: STOP. Report the problem. Ask whether to wait or try Bywater (Caruana) as the alternate Headwater host. Never silently switch to haiku, gpt-mini, sonnet, opus, gemini, etc.

### CLI First

Always attempt CLI invocations first. Only fall back to direct server/database/client calls (HeadwaterAsyncClient, psql, etc.) when the CLI hits a genuine technical roadblock.

For Headwater inference, try `conduit query --model gpt-oss` first. If the CLI is misconfigured or routing incorrectly, that counts as a roadblock — escalate to HeadwaterAsyncClient only then.

---

## Nimzo VPS

- IP: 204.168.191.144 / SSH alias: `nimzo` / User: root / Key: `~/.ssh/Petrosian`
- Purpose: public-facing VPS, running Stalwart Mail Server for newsletter ingestion
- Stalwart: self-hosted IMAP/JMAP/SMTP; app password auth (no OAuth)

## Newsletter Source (in progress)

- Protocol: IMAP against Stalwart on nimzo
- Credentials via env: `NEWSLETTER_IMAP_HOST`, `NEWSLETTER_IMAP_USER`, `NEWSLETTER_IMAP_PASSWORD`
- URI scheme: `newsletter:///<sender_domain>/<message_id>`
- Extraction: HTML → markdown via readabilipy + markdownify
- CLI: `siphon fetch newsletters`
- Checkpoint: timestamp + message-ID set in Postgres (append-only, no automated pruning)
