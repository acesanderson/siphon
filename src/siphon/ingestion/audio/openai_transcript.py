from openai import OpenAI
from pathlib import Path
import os

# Import our centralized logger - no configuration needed here!
from siphon.logs.logging_config import get_logger

# Get logger for this module - will inherit config from retrieve_audio.py
logger = get_logger(__name__)


api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=api_key)


def get_openai_transcript(audio_file: str | Path):
    """
    Use the transcriptions API endpoint.
    We didn't implement this in Conduit since it's really tied to a transcription use case.
    """
    if isinstance(audio_file, str):
        audio_file = Path(audio_file)
    extension = audio_file.suffix.lower()
    if extension[1:] not in ["mp3", "wav"]:
        raise ValueError("Wrong extension; whisper only handles mp3 and wav.")
    else:
        logger.info(f"Transcribing {audio_file} with OpenAI Whisper API.")
        with open(audio_file, "rb") as f:
            transcript = openai_client.audio.transcriptions.create(
                file=f,
                model="whisper-1",
            )
    return transcript.text
