#!/usr/bin/env bash
# Upload a local audio file to a worker on alphablue and print the JSON response.
#
# Usage: worker_test.sh <local_audio_path> [port]
# Example: bash scripts/worker_test.sh $RECORDINGS/people_inc.mp3 8003

set -euo pipefail

AUDIO_PATH="${1:?Usage: worker_test.sh <local_audio_path> [port]}"
PORT="${2:-8003}"

REMOTE_TMP="/tmp/siphon_test_$(basename "$AUDIO_PATH")"

echo "==> uploading $(basename "$AUDIO_PATH") to alphablue ..."
scp "$AUDIO_PATH" "alphablue:$REMOTE_TMP"

echo "==> calling localhost:$PORT/process ..."
ssh alphablue "curl -s -X POST http://localhost:$PORT/process -F \"file=@$REMOTE_TMP\"" \
    | python3 -m json.tool

echo "==> cleaning up ..."
ssh alphablue "rm -f $REMOTE_TMP"
