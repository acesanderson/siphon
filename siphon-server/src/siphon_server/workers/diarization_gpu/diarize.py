import logging
import os
import threading
import torch
from pathlib import Path

# torchaudio 2.7+ removed AudioMetaData from the top-level module, but
# pyannote.audio 3.3.2 references it as a type annotation in io.py at import
# time. Patch it back before importing pyannote so the annotation resolves.
import torchaudio
if not hasattr(torchaudio, 'AudioMetaData'):
    try:
        from torchaudio.backend.common import AudioMetaData as _AM
        torchaudio.AudioMetaData = _AM
    except ImportError:
        try:
            from torchaudio._backend.common import AudioMetaData as _AM
            torchaudio.AudioMetaData = _AM
        except ImportError:
            from collections import namedtuple
            torchaudio.AudioMetaData = namedtuple(
                'AudioMetaData',
                ['sample_rate', 'num_frames', 'num_channels', 'bits_per_sample', 'encoding'],
            )

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
    return _pipeline(str(audio_file))
