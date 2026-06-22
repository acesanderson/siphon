#!/usr/bin/env bash
# List Ollama model names from Drive_B manifests and show core_models.txt.
# Usage: bash scripts/driveb_models.sh

set -euo pipefail
HOST="alphablue"

echo "=== core_models.txt ==="
ssh "$HOST" "cat /mnt/Drive_B/ollama-models/core_models.txt 2>/dev/null || echo '(not found)'"

echo ""
echo "=== models from manifests ==="
ssh "$HOST" "find /mnt/Drive_B/ollama-models/manifests -type f 2>/dev/null | sed 's|.*/manifests/||' | sort"

echo ""
echo "=== llama.cpp models ==="
ssh "$HOST" "ls -lh /mnt/Drive_B/llama-cpp-models/"
