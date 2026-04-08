import numpy as np
import wave
from transformers import pipeline
import torch


def load_transcriber():
    return pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-large-v3",
        return_timestamps="sentence",
        device=0,
        torch_dtype=torch.float16,
    )


# Module-level singleton — loaded once on startup
_transcriber = load_transcriber()


def run_transcription(wav_path: str) -> list[dict]:
    with wave.open(wav_path, "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
    audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)
    audio /= np.iinfo(dtype).max

    result = _transcriber({"raw": audio, "sampling_rate": sample_rate})
    return [
        {
            "text": chunk["text"],
            "start": chunk["timestamp"][0],
            "end": chunk["timestamp"][1],
        }
        for chunk in result.get("chunks", [])
    ]
