from pathlib import Path
from transformers import pipeline
import torch

# Import our centralized logger - no configuration needed here!
from siphon.logs.logging_config import get_logger

# Get logger for this module - will inherit config from retrieve_audio.py
logger = get_logger(__name__)


# Transcript workflow
def transcribe(file_name: str | Path) -> str:
    """
    Use Whisper to retrieve text content + timestamps.
    """
    transcriber = pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-base",
        # model="openai/whisper-large-v3",
        return_timestamps="sentence",
        device=0,
        torch_dtype=torch.float16,
    )
    logger.info(f"Transcribing file: {file_name}")
    result = transcriber(file_name)
    return result


if __name__ == "__main__":
    ASSETS_PATH = Path(__file__).parent.parent.parent.parent.parent / "assets"
    EXAMPLE_AUDIO = ASSETS_PATH / "example.mp3"
    transcript = transcribe(str(EXAMPLE_AUDIO))
    print("Transcription Result:")
    print(transcript)
