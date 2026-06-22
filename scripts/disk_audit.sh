#!/usr/bin/env bash
# Audit disk usage on alphablue to identify bloat candidates.
# Usage: bash scripts/disk_audit.sh

set -euo pipefail

HOST="alphablue"

echo "=== overall disk ==="
ssh "$HOST" "df -h /"

echo ""
echo "=== top-level /home/fishhouses ==="
ssh "$HOST" "du -sh /home/fishhouses/*/  2>/dev/null | sort -rh | head -20" || true

echo ""
echo "=== HF cache (user) ==="
ssh "$HOST" "du -sh /home/fishhouses/.cache/huggingface 2>/dev/null || echo '(not found)'"

echo ""
echo "=== HF cache (root) ==="
ssh "$HOST" "sudo du -sh /root/.cache/huggingface 2>/dev/null || echo '(not found)'"

echo ""
echo "=== Docker disk usage ==="
ssh "$HOST" "docker system df"

echo ""
echo "=== Docker images (all) ==="
ssh "$HOST" "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}'"

echo ""
echo "=== Docker volumes ==="
ssh "$HOST" "docker volume ls -q | xargs -r docker volume inspect --format '{{.Name}} => {{.Mountpoint}}'"

echo ""
echo "=== /var/lib/docker breakdown ==="
ssh "$HOST" "sudo du -sh /var/lib/docker/*/  2>/dev/null | sort -rh | head -20" || true

echo ""
echo "=== /tmp ==="
ssh "$HOST" "du -sh /tmp 2>/dev/null || echo '(empty or inaccessible)'"

echo ""
echo "=== largest files under /home/fishhouses (top 20) ==="
ssh "$HOST" "find /home/fishhouses -type f -size +500M 2>/dev/null | xargs -r du -sh | sort -rh | head -20" || true

echo ""
echo "=== largest dirs under / excluding /proc /sys /dev (top 20) ==="
ssh "$HOST" "sudo du -sh --exclude=/proc --exclude=/sys --exclude=/dev /* 2>/dev/null | sort -rh | head -20" || true
