#!/usr/bin/env bash
# Check disk space, running containers, and health endpoints on alphablue.
#
# Usage: worker_status.sh [port...]
# Example: bash scripts/worker_status.sh 8000 8002 8003

set -euo pipefail

HOST="alphablue"
PORTS=("${@:-8000 8002 8003}")

echo "=== disk ==="
ssh "$HOST" "df -h /"

echo ""
echo "=== containers ==="
ssh "$HOST" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo ""
echo "=== health ==="
for port in "${PORTS[@]}"; do
    result=$(ssh "$HOST" "curl -s --max-time 3 http://localhost:$port/health 2>/dev/null || echo '{\"status\":\"unreachable\"}'")
    echo "  :$port => $result"
done
