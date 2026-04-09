import logging
import os
import threading
import torch
import numpy as np
import soundfile as sf
from pathlib import Path
from pyannote.audio import Pipeline
from pyannote.core import Annotation

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_pipeline = None
_ready = False
_error: str | None = None


def load_model_background():
    """Load model in a background thread so the server can start accepting requests immediately."""
    global _pipeline, _ready, _error
    try:
        logger.info("[DIARIZE] Starting model load...")
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
        assert hf_token, "HUGGINGFACEHUB_API_TOKEN environment variable is not set"
        logger.info("[DIARIZE] Fetching pyannote/speaker-diarization-3.1 from HuggingFace...")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
        logger.info("[DIARIZE] Moving pipeline to CUDA...")
        _pipeline.to(torch.device("cuda"))
        _ready = True
        logger.info("[DIARIZE] Model ready.")
    except Exception as e:
        _error = str(e)
        logger.error(f"[DIARIZE] Model load failed: {e}")


def start_loading():
    thread = threading.Thread(target=load_model_background, daemon=True)
    thread.start()


def is_ready() -> bool:
    return _ready


def get_error() -> str | None:
    return _error


def run_diarization(audio_file: Path) -> Annotation:
    if not _ready:
        raise RuntimeError("Model not yet loaded")
    # Preload audio via soundfile to bypass torchcodec dependency in pyannote.audio 4.x.
    # pyannote accepts {'waveform': (channels, time) tensor, 'sample_rate': int}.
    waveform, sample_rate = sf.read(str(audio_file), dtype="float32")
    if waveform.ndim == 1:
        waveform = waveform[np.newaxis, :]  # mono: (time,) → (1, time)
    else:
        waveform = waveform.T  # soundfile: (time, channels) → (channels, time)
    waveform_tensor = torch.from_numpy(waveform)
    audio_dict = {"waveform": waveform_tensor, "sample_rate": sample_rate}
    return _pipeline(audio_dict)
