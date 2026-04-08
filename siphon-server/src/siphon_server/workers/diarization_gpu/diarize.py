import os
import torch
from pathlib import Path
from pyannote.audio import Pipeline
from pyannote.core import Annotation

_pipeline = None


def load_model():
    global _pipeline
    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    assert hf_token, "HUGGINGFACEHUB_API_TOKEN environment variable is not set"
    _pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )
    _pipeline.to(torch.device("cuda"))


def run_diarization(audio_file: Path) -> Annotation:
    if _pipeline is None:
        raise RuntimeError("Model not loaded — call load_model() first")
    return _pipeline(str(audio_file))
