FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04
WORKDIR /app

RUN apt-get update && apt-get install -y python3.11 python3-pip ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv pip install --system torch --index-url https://download.pytorch.org/whl/cu128
RUN uv pip install --system "pyannote.audio>=4.0" fastapi "uvicorn[standard]" python-multipart

COPY diarize.py .
COPY main.py .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
