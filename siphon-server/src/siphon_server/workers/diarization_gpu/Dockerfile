FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04
WORKDIR /app

RUN apt-get update && apt-get install -y python3.11 python3-pip ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv pip install --system torch torchaudio --index-url https://download.pytorch.org/whl/cu128
RUN uv pip install --system "pyannote.audio>=4.0" fastapi "uvicorn[standard]" python-multipart

# pyannote.audio 4.x has a bug where some pipeline files reference AudioDecoder
# without importing it. Patch every file that uses AudioDecoder but doesn't import it.
RUN python3 -c "
import pathlib
base = pathlib.Path('/usr/local/lib/python3.10/dist-packages/pyannote/audio')
io_file = base / 'core' / 'io.py'
for f in base.rglob('*.py'):
    if f == io_file:
        continue
    content = f.read_text()
    if 'AudioDecoder' in content and 'AudioDecoder' not in content.split('AudioDecoder')[0].split('\n')[-1]:
        if 'from pyannote.audio.core.io import AudioDecoder' not in content:
            content = 'from pyannote.audio.core.io import AudioDecoder\n' + content
            f.write_text(content)
            print(f'Patched: {f}')
"

COPY diarize.py .
COPY main.py .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
