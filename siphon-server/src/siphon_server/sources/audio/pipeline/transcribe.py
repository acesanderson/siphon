from __future__ import annotations

import platform
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def transcribe(file_name: str | Path) -> list[dict]:
    """
    Transcribe audio file using the appropriate backend for the current platform.

    Returns a normalized list of chunks: [{text: str, start: float, end: float}]
    """
    file_name = str(file_name)
    if _is_apple_silicon():
        return _transcribe_mlx(file_name)
    else:
        return _transcribe_hf(file_name)


def _transcribe_mlx(file_name: str) -> list[dict]:
    import mlx_whisper
    logger.debug(f"[TRANSCRIBE] Using mlx-whisper (Apple Silicon): {file_name}")
    result = mlx_whisper.transcribe(
        file_name,
        path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
    )
    return [
        {"text": seg["text"], "start": seg["start"], "end": seg["end"]}
        for seg in result.get("segments", [])
    ]


def _transcribe_hf(file_name: str) -> list[dict]:
    import wave
    import numpy as np
    from transformers import pipeline
    import torch
    logger.debug(f"[TRANSCRIBE] Using HF transformers (CUDA): {file_name}")

    # Read WAV as numpy array to avoid transformers' internal ffmpeg PATH dependency
    with wave.open(file_name, "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
    audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)
    audio /= np.iinfo(dtype).max

    transcriber = pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-large-v3",
        return_timestamps="sentence",
        device=0,
        torch_dtype=torch.float16,
    )
    result = transcriber({"raw": audio, "sampling_rate": sample_rate})
    return [
        {
            "text": chunk["text"],
            "start": chunk["timestamp"][0],
            "end": chunk["timestamp"][1],
        }
        for chunk in result.get("chunks", [])
    ]
