#!/usr/bin/env bash
# Sync siphon code changes to remote hosts.
#
# Usage:
#   ./scripts/deploy.sh [--restart-workers] [caruana|alphablue|all]
#
# Targets:
#   caruana   — pull on caruana
#   alphablue — pull on alphablue
#   all       — both (default)
#
# --restart-workers: rebuild and restart Docker worker sidecars on alphablue
#                    (needed when worker code or Dockerfile changed)

set -euo pipefail

LOCAL_REPO="$HOME/Brian_Code/siphon"

declare -A REMOTE_REPO=(
    [caruana]="/home/bianders/Brian_Code/siphon"
    [alphablue]="/home/fishhouses/Brian_Code/siphon"
)

declare -A REMOTE_DBCLIENTS=(
    [caruana]="/home/bianders/Brian_Code/dbclients-project"
    [alphablue]="/home/fishhouses/Brian_Code/dbclients-project"
)

WORKERS_ALPHABLUE=(
    "siphon-server/src/siphon_server/workers/diarization_gpu"
    "siphon-server/src/siphon_server/workers/whisper_gpu"
)
WORKER_PORTS=(
    8000
    8002
)

# Legacy workers to stop before bringing up new ones (port conflicts)
LEGACY_WORKERS_ALPHABLUE=(
    "siphon-server/src/siphon_server/workers/diarization_cpu"
)

# --- parse args ---
RESTART_WORKERS=0
TARGET="all"

for arg in "$@"; do
    case "$arg" in
        --restart-workers) RESTART_WORKERS=1 ;;
        caruana|alphablue|all) TARGET="$arg" ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# --- push local changes ---
echo "==> pushing to origin..."
git -C "$LOCAL_REPO" push

# --- pull on each target ---
remote_pull() {
    local host="$1"
    local repo="${REMOTE_REPO[$host]}"
    echo "==> [$host] pulling code..."
    ssh "$host" "git -C $repo pull --ff-only https://${GITHUB_PERSONAL_TOKEN}@github.com/acesanderson/siphon.git"
    echo "==> [$host] pulling dbclients..."
    ssh -A "$host" "git -C ${REMOTE_DBCLIENTS[$host]} pull --ff-only" || echo "==> [$host] dbclients pull failed (SSH agent not forwarded?) — skipping"
    echo "==> [$host] syncing dependencies..."
    ssh "$host" "cd $repo/siphon-server && uv sync"
}

remote_restart_workers() {
    local host="$1"
    local repo="${REMOTE_REPO[$host]}"
    local num_workers="${#WORKERS_ALPHABLUE[@]}"

    # Stop any legacy workers that may conflict on the same ports
    for legacy_dir in "${LEGACY_WORKERS_ALPHABLUE[@]}"; do
        local legacy_compose="$repo/$legacy_dir/docker-compose.yml"
        echo "==> [$host] stopping legacy worker: $legacy_dir ..."
        ssh "$host" "[ -f $legacy_compose ] && docker compose -f $legacy_compose down 2>/dev/null || true"
    done

    for (( i=0; i<num_workers; i++ )); do
        local worker_dir="${WORKERS_ALPHABLUE[$i]}"
        local port="${WORKER_PORTS[$i]}"
        local full_path="$repo/$worker_dir"
        local compose_file="$full_path/docker-compose.yml"
        # Derive compose project name (directory basename)
        local project_name
        project_name=$(basename "$full_path")

        echo "==> [$host] rebuilding worker: $worker_dir ..."
        # Bring down first to clear any cached state, then rebuild
        ssh "$host" "docker compose -f $compose_file down 2>/dev/null || true"
        # NOTE: hf_cache volume is intentionally preserved across restarts to avoid
        # re-downloading large models. Only delete manually if you need to bust
        # a stale 403 auth cache: docker volume rm ${project_name}_hf_cache
        ssh "$host" "docker compose -f $compose_file up -d --build"

        echo -n "==> [$host] waiting for worker on :$port ... "
        local last_status=""
        for j in $(seq 1 300); do
            status=$(ssh "$host" "curl -sf http://localhost:$port/health 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('status',''))\" 2>/dev/null" 2>/dev/null || true)
            last_status="$status"
            if [[ "$status" == "healthy" ]]; then
                echo "up"
                break
            elif [[ "$status" == "error" ]]; then
                echo "ERROR — model failed to load"
                echo "--- container logs ---"
                ssh "$host" "docker compose -f $compose_file logs --tail=50" || true
                exit 1
            fi
            if [[ $j -eq 300 ]]; then
                echo "TIMEOUT after 300s (last status: ${last_status:-no response})"
                echo "--- container logs ---"
                ssh "$host" "docker compose -f $compose_file logs --tail=50" || true
                exit 1
            fi
            sleep 1
        done
    done
}

case "$TARGET" in
    caruana)
        remote_pull caruana
        ;;
    alphablue)
        remote_pull alphablue
        if [[ "$RESTART_WORKERS" -eq 1 ]]; then
            remote_restart_workers alphablue
        fi
        ;;
    all)
        remote_pull caruana
        remote_pull alphablue
        if [[ "$RESTART_WORKERS" -eq 1 ]]; then
            remote_restart_workers alphablue
        fi
        ;;
esac

echo "==> sync complete"
