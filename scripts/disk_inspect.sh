#!/usr/bin/env bash
# Inspect unallocated/unmounted partitions to inform a storage strategy.
# Usage: bash scripts/disk_inspect.sh

set -euo pipefail

HOST="alphablue"

echo "=== lsblk with filesystem info ==="
ssh "$HOST" "lsblk -f"

echo ""
echo "=== all current mounts ==="
ssh "$HOST" "findmnt --real"

echo ""
echo "=== fstab ==="
ssh "$HOST" "cat /etc/fstab"

echo ""
echo "=== check if nvme0n1p3 has a filesystem (no sudo) ==="
ssh "$HOST" "file -s /dev/nvme0n1p3 2>/dev/null || echo '(permission denied)'"
ssh "$HOST" "file -s /dev/nvme1n1p1 2>/dev/null || echo '(permission denied)'"
ssh "$HOST" "file -s /dev/nvme2n1p1 2>/dev/null || echo '(permission denied)'"
