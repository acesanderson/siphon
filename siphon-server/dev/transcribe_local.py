"""
Local transcription test script.
Usage: python dev/transcribe_local.py <audio_file>
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siphon_server.sources.audio.pipeline.audio_pipeline import retrieve_audio


def main():
    if len(sys.argv) < 2:
        print("Usage: transcribe_local.py <audio_file>")
        sys.exit(1)

    audio_path = Path(sys.argv[1]).expanduser().resolve()
    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        sys.exit(1)

    print(f"Transcribing: {audio_path}")
    result = retrieve_audio(audio_path, diarize=False)
    print(result)


if __name__ == "__main__":
    main()
