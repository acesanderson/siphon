#!/usr/bin/env bash
# Free Docker build cache and start a worker container without rebuilding.
# Use when the image is already built but the container failed to start
# (e.g. due to disk space errors during the build metadata write).
#
# Usage: worker_start.sh <host> <worker_dir> <port>
# Example: bash scripts/worker_start.sh alphablue \
#            siphon-server/src/siphon_server/workers/granite_speech_gpu 8003

set -euo pipefail

HOST="${1:?Usage: worker_start.sh <host> <worker_dir> <port>}"
WORKER_DIR="${2:?Usage: worker_start.sh <host> <worker_dir> <port>}"
PORT="${3:?Usage: worker_start.sh <host> <worker_dir> <port>}"

declare -A REMOTE_REPO=(
    [caruana]="/home/bianders/Brian_Code/siphon"
    [alphablue]="/home/fishhouses/Brian_Code/siphon"
)

REPO="${REMOTE_REPO[$HOST]:?Unknown host: $HOST}"
COMPOSE_FILE="$REPO/$WORKER_DIR/docker-compose.yml"

echo "==> [$HOST] pruning Docker build cache..."
ssh "$HOST" "docker builder prune -af"
ssh "$HOST" "echo '--- disk after prune ---' && df -h /"

echo "==> [$HOST] starting $WORKER_DIR (no rebuild)..."
ssh "$HOST" "docker compose -f $COMPOSE_FILE up -d"

echo -n "==> [$HOST] waiting for worker on :$PORT "
last_status=""
for i in $(seq 1 300); do
    status=$(ssh "$HOST" "curl -sf http://localhost:$PORT/health 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('status',''))\" 2>/dev/null" 2>/dev/null || true)
    last_status="$status"
    if [[ "$status" == "healthy" ]]; then
        echo "up"
        break
    elif [[ "$status" == "error" ]]; then
        echo "ERROR"
        ssh "$HOST" "docker compose -f $COMPOSE_FILE logs --tail=50"
        exit 1
    fi
    if [[ $i -eq 300 ]]; then
        echo "TIMEOUT (last status: ${last_status:-no response})"
        ssh "$HOST" "docker compose -f $COMPOSE_FILE logs --tail=50"
        exit 1
    fi
    printf "."
    sleep 1
done
