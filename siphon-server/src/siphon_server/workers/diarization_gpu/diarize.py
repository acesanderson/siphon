import os
import threading
import torch
from pathlib import Path
from pyannote.audio import Pipeline
from pyannote.core import Annotation

_pipeline = None
_ready = False
_error: str | None = None


def load_model_background():
    """Load model in a background thread so the server can start accepting requests immediately."""
    global _pipeline, _ready, _error
    try:
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
        assert hf_token, "HUGGINGFACEHUB_API_TOKEN environment variable is not set"
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        _pipeline.to(torch.device("cuda"))
        _ready = True
    except Exception as e:
        _error = str(e)


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
