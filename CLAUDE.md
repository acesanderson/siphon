# Siphon — Agent Development Guide

Siphon is a media processing pipeline (audio transcription, diarization, image generation) that runs on two Linux hosts. This file tells you how to develop, deploy, and debug it as a coding agent.

---

## Active Work — Enrichment + Retrieval Refactor

**Status as of 2026-06-21.**

**Shipped to date:**
- Phase 3 conduit-side: `RoutingSummarizer` + `SummarizationProfile` + `_TextInput.guideline` (`b3f3157`, deployed 2026-06-01).
- Article migrated to the new pattern (`040cfe3`). All 9 other implemented enrichers followed (`2b39ca9`).
- Phase R1 article HyDE description (`83fbb23`). Phase R5 HyDE description rollout to all 9 other sources (`11cbab6`).
- Phase R2-R4 scaffolding (`56a47a7`) but not run.
- Layer 1 observability shipped 2026-06-21 (`8e7194a` siphon, `b1cdfe6` + `0578342` conduit). `enrichment_runs` table, `siphon inspect <uri>` CLI, conduit `rendered_prompt` metadata for forensic-grade traces.
- Routing fix 2026-06-21 (`0578342`): Tier 1 upper bound dropped 12K → 5K after empirical confirmation via the new trace that the gpt-oss ECW cliff was causing hallucinated CTA boilerplate on 5K-12K inputs (`youtube:///Kf0rPU7zy7Q` was the canary).

**Pick up here next session:**

1. **Read `siphon-server/dev/summarization.md`** — enrichment architecture, observability design (Layers 1/2/3), canonical enricher shape.
2. **Read `siphon-server/dev/retrieval.md`** — embedding migration plan, HyDE description design, RRF query pipeline.
3. **Conduit-side context** — `$BC/conduit-project/evals/STRATEGY.md` for routing decision rationale and the dropped models (qwen3.6 latency, MapDedupeReduce no quality niche).

**Recommended next action: Phase R2-R4 in `retrieval.md`.** The embedding migration is the largest unblocked item on the roadmap. New HyDE-shaped descriptions are currently being truncated at 256 tokens by the legacy `all-MiniLM-L6-v2` encoder, so the R5 rollout is partly cosmetic until R2-R4 lands. Sequence: confirm `nomic-embed-text-v2` reachable on backwater, flip `EMBED_DIM` to 768, rewrite `get_embed_texts()` to return description only, drop+rebuild HNSW, NULL existing embeddings, then re-embed all rows after regenerating descriptions.

**Smaller follow-ups worth queuing:**

- **Re-enrich stale rows in the 5K-12K dead band.** URIs enriched before today's routing fix still hold the bad summaries in `processed_content`. Once enough new `enrichment_runs` rows accumulate, a query like `WHERE tier = 'tier1_oneshot_gpt_oss' AND token_count BETWEEN 5000 AND 12000` identifies candidates. Trace data only exists going forward, so this is opportunistic cleanup, not bulk.
- **Layer 3 observability TBD.** Nightly Cronicle job that samples production `enrichment_runs` and re-scores with the Gemini3 judge. Defer until there's a steady stream of rows to sample.
- **Description guideline hash.** Currently only summary guideline is hashed into `enrichment_runs.guideline_hash`. Description guideline isn't tracked. When R2-R4 lands and description iteration picks up, worth adding a second hash field.
- **Drive enricher (`NotImplementedError` stub) and podcasts enricher (no `enricher.py`).** Both need upstream work before they join the migration. Not blocking anything.

**Operational follow-ups (not roadmap, but worth not losing):**

- **Alphablue `uv` not on non-interactive PATH.** Every conduit/siphon deploy hits "uv: command not found" during the remote `uv sync` step on alphablue. Pulls succeed, sync fails. Today this is harmless (no new deps), but the next `pyproject.toml` change will need this fixed first. Likely a `.bashrc` vs `.bash_profile` issue.
- **Cronicle event `emothl43a01`** (conduit eval rerun) still times out at the 4h Cronicle limit and writes 0-byte NAS logs. Tier 3 routing settles on whatever wins this rerun (`PRODUCTION_ROUTING` swap is one line post-rerun).

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
