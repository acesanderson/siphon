#!/usr/bin/env bash
# Sync siphon code changes to remote hosts.
#
# Usage:
#   ./scripts/deploy.sh [caruana|alphablue|all]
#
# Targets:
#   caruana   — pull on caruana
#   alphablue — pull on alphablue
#   all       — both (default)

set -euo pipefail

LOCAL_REPO="$HOME/Brian_Code/siphon"

declare -A REMOTE_REPO=(
    [caruana]="/home/bianders/Brian_Code/siphon"
    [alphablue]="/home/fishhouses/Brian_Code/siphon"
)

# --- parse args ---
TARGET="${1:-all}"

case "$TARGET" in
    caruana|alphablue|all) ;;
    *) echo "Unknown argument: $TARGET"; exit 1 ;;
esac

# --- push local changes ---
echo "==> pushing to origin..."
git -C "$LOCAL_REPO" push

# --- pull on each target ---
remote_pull() {
    local host="$1"
    local repo="${REMOTE_REPO[$host]}"
    echo "==> [$host] pulling code..."
    ssh "$host" "git -C $repo pull --ff-only https://${GITHUB_PERSONAL_TOKEN}@github.com/acesanderson/siphon.git"
}

case "$TARGET" in
    caruana)   remote_pull caruana ;;
    alphablue) remote_pull alphablue ;;
    all)       remote_pull caruana; remote_pull alphablue ;;
esac

echo "==> sync complete"
