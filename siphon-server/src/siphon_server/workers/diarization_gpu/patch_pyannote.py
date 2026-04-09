"""
Build-time patch: add missing AudioDecoder import to pyannote.audio 4.x files
that reference the class without importing it.
"""
import pathlib

base = pathlib.Path("/usr/local/lib/python3.10/dist-packages/pyannote/audio")
io_file = base / "core" / "io.py"

for f in base.rglob("*.py"):
    if f == io_file:
        continue
    content = f.read_text()
    if "AudioDecoder" not in content:
        continue
    if "from pyannote.audio.core.io import AudioDecoder" in content:
        continue
    content = "from pyannote.audio.core.io import AudioDecoder\n" + content
    f.write_text(content)
    print(f"Patched: {f}")

print("Patch complete.")
