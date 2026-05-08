#!/usr/bin/env bash
# Fetch logs from a worker container on a remote host.
#
# Usage: worker_logs.sh <host> <worker_dir> [tail_lines]
# Example: bash scripts/worker_logs.sh alphablue \
#            siphon-server/src/siphon_server/workers/granite_speech_gpu 200

set -euo pipefail

HOST="${1:?Usage: worker_logs.sh <host> <worker_dir> [tail_lines]}"
WORKER_DIR="${2:?Usage: worker_logs.sh <host> <worker_dir> [tail_lines]}"
TAIL="${3:-100}"

declare -A REMOTE_REPO=(
    [caruana]="/home/bianders/Brian_Code/siphon"
    [alphablue]="/home/fishhouses/Brian_Code/siphon"
)

REPO="${REMOTE_REPO[$HOST]:?Unknown host: $HOST}"
COMPOSE_FILE="$REPO/$WORKER_DIR/docker-compose.yml"

ssh "$HOST" "docker compose -f $COMPOSE_FILE logs --tail=$TAIL"
