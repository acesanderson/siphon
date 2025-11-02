from siphon.ingestion.audio.local_transcript import get_local_transcript
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
assert ASSETS_DIR.exists()
