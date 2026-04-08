FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04
WORKDIR /app

RUN apt-get update && apt-get install -y python3.11 python3-pip ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv pip install --system torch --index-url https://download.pytorch.org/whl/cu128
RUN uv pip install --system transformers accelerate numpy fastapi "uvicorn[standard]" python-multipart

COPY transcribe.py .
COPY main.py .

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
