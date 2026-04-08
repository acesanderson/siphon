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

WORKERS_ALPHABLUE=(
    "siphon-server/src/siphon_server/workers/whisper_gpu"
)
WORKER_PORTS=(
    8002
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
    echo "==> [$host] syncing dependencies..."
    ssh "$host" "cd $repo/siphon-server && uv sync"
}

remote_restart_workers() {
    local host="$1"
    local repo="${REMOTE_REPO[$host]}"
    local num_workers="${#WORKERS_ALPHABLUE[@]}"

    for (( i=0; i<num_workers; i++ )); do
        local worker_dir="${WORKERS_ALPHABLUE[$i]}"
        local port="${WORKER_PORTS[$i]}"
        local full_path="$repo/$worker_dir"
        local compose_file="$full_path/docker-compose.yml"

        echo "==> [$host] rebuilding worker: $worker_dir ..."
        ssh "$host" "docker compose -f $compose_file up -d --build"

        echo -n "==> [$host] waiting for worker on :$port ... "
        for j in $(seq 1 120); do
            if ssh "$host" "curl -sf http://localhost:$port/health" > /dev/null 2>&1; then
                echo "up"
                break
            fi
            if [[ $j -eq 120 ]]; then
                echo "TIMEOUT after 120s"
                echo "    run: ssh $host 'docker compose -f $compose_file logs' for details"
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
