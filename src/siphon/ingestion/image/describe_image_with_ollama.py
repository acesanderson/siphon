from conduit.message.convert_image import convert_image_file
from pathlib import Path

# Import our centralized logger - no configuration needed here!
from siphon.logs.logging_config import get_logger

# Get logger for this module - will inherit config from retrieve_audio.py
logger = get_logger(__name__)


def describe_image_with_ollama_models(file_path: str | Path, model="gemma3:27b") -> str:
    import ollama

    logger.info(f"Converting image file {file_path} to Ollama-compatible format.")
    image_data = convert_image_file(file_path)
    # Send the image to a vision-capable model (e.g., 'llava')
    logger.info(f"Sending image data to Ollama model: {model}")
    response = ollama.generate(
        model=model,
        prompt="Describe this photo in detail. If there is text in the image, return it verbatim.",
        images=[image_data],
        keep_alive=0,
    )
    logger.info("Received response from Ollama model.")
    return response["response"]
