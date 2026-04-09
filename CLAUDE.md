# Siphon — Agent Development Guide

Siphon is a media processing pipeline (audio transcription, diarization, image generation) that runs on two Linux hosts. This file tells you how to develop, deploy, and debug it as a coding agent.

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
