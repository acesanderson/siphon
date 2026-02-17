import os
from pathlib import Path
import logging
from siphon_api.file_types import EXTENSIONS

# Set up logging
log_level = int(os.getenv("PYTHON_LOG_LEVEL", "3"))
levels = {1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
logging.basicConfig(
    level=levels.get(log_level, logging.INFO), format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def retrieve_audio(audio_path: Path) -> str:
    suffix = audio_path.suffix.lower()
    if suffix not in EXTENSIONS["Audio"]:
        raise ValueError(f"Unsupported audio format: {suffix}")

    logger.info("[AUDIO PIPELINE] Starting audio processing pipeline")

    from siphon_server.sources.audio.pipeline.preprocess import guaranteed_wav_path
    from siphon_server.sources.audio.pipeline.diarize import diarize
    from siphon_server.sources.audio.pipeline.transcribe import transcribe
    from siphon_server.sources.audio.pipeline.combine import combine
    from siphon_server.sources.audio.pipeline.format import format

    try:
        with guaranteed_wav_path(audio_path) as wav_path:
            logger.info("[AUDIO PIPELINE] Starting diarization")
            diarization_response = diarize(wav_path)
            logger.info("[AUDIO PIPELINE] Starting transcription")
            transcript = transcribe(wav_path)
            logger.info("[AUDIO PIPELINE] Combining diarization and transcription")
            combined = combine(diarization_response, transcript)
            logger.info("[AUDIO PIPELINE] Formatting the final output")
            formatted = format(combined)
        assert formatted is not None, "Formatted output should not be None"
    except Exception as e:
        logger.error(f"Error during audio processing: {e}")
        raise e

    logger.info("[AUDIO PIPELINE] Audio processing pipeline completed successfully")
    return formatted


if __name__ == "__main__":
    audio_path = Path(__file__).parent / "occupation.mp3"
    result = retrieve_audio(audio_path)
    print(result)
