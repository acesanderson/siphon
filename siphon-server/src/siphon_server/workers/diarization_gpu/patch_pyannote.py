"""
Build-time patch / diagnostic for pyannote.audio AudioDecoder issue.
Searches ALL .py files (including io.py) for AudioDecoder references and reports.
Then adds missing import to any file that uses AudioDecoder without importing it.
"""
import pathlib

base = pathlib.Path("/usr/local/lib/python3.10/dist-packages/pyannote/audio")
io_file = base / "core" / "io.py"

# Report pyannote version
try:
    import pyannote.audio
    print(f"pyannote.audio version: {pyannote.audio.__version__}")
except Exception as e:
    print(f"Could not get version: {e}")

# Check if AudioDecoder exists in io.py
if io_file.exists():
    io_content = io_file.read_text()
    has_decoder_def = "class AudioDecoder" in io_content or "AudioDecoder" in io_content
    print(f"io.py contains 'AudioDecoder': {has_decoder_def}")
    if "AudioDecoder" in io_content:
        # Find the lines
        for i, line in enumerate(io_content.splitlines(), 1):
            if "AudioDecoder" in line:
                print(f"  io.py:{i}: {line.rstrip()}")
else:
    print("io.py not found!")

# Search all .py files for AudioDecoder
print("\nAll .py files referencing AudioDecoder:")
for f in sorted(base.rglob("*.py")):
    content = f.read_text()
    if "AudioDecoder" not in content:
        continue
    rel = f.relative_to(base)
    imported = "from pyannote.audio.core.io import AudioDecoder" in content
    print(f"  {rel} (imported={imported})")
    if not imported and f != io_file:
        print(f"    -> PATCHING: adding import")
        content = "from pyannote.audio.core.io import AudioDecoder\n" + content
        f.write_text(content)

print("\nDone.")
