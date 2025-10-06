from pathlib import Path


from typing import Literal

# Import our centralized logging configuration
from siphon.logs.logging_config import get_logger

# Configure logging once at the entry point
logger = get_logger(__name__)


def retrieve_image(image_path: str | Path, model: Literal["local", "cloud"]) -> str:
    """
    Retrieves an image description using the specified model.

    Args:
        image_path (str | Path): The path to the image file.
        model (str): The model to use for image description. Options are "ollama" or any Conduit-supported model.

    Returns:
        str: The description of the image.
    """
    if model == "cloud":
        from siphon.ingestion.image.describe_image_with_cloud import (
            describe_image_with_cloud_models,
        )

        logger.info(f"Starting image description process with Conduit model: {model}")
        return describe_image_with_cloud_models(image_path, model="gpt-4.1-mini")
    elif model == "local":
        from siphon.ingestion.image.describe_image_with_ollama import (
            describe_image_with_ollama_models,
        )

        logger.info("Starting image description process with Ollama models.")
        return describe_image_with_ollama_models(image_path)
