from pathlib import Path
from conduit.sync import Model
from conduit.message.imagemessage import ImageMessage

# Import our centralized logger - no configuration needed here!
from siphon.logs.logging_config import get_logger

# Get logger for this module - will inherit config from retrieve_audio.py
logger = get_logger(__name__)


def describe_image_with_cloud_models(file_path: str | Path, model="gpt") -> str:
    """
    Describe an image using a Conduit model.
    TBD: implement Ollama.
    """
    prompt_str = "Please describe this image in detail. If it is full of text, please provide the text verbatim."
    imagemessage = ImageMessage.from_image_file(
        role="user", image_file=file_path, text_content=prompt_str
    )

    logger.info(f"Creating Conduit model with name: {model}")
    model = Model(model)
    logger.info(f"Running query with model: {model.model} and image: {file_path}")
    response = model.query(imagemessage)
    return str(response.content)
