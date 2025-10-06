from siphon.data.type_definitions.extensions import Extensions as extensions
from pydantic import BaseModel, Field
import re, base64
from pathlib import Path


def is_base64_simple(s):
    """
    Simple validation for base64 strings.
    """
    return bool(re.match(r"^[A-Za-z0-9+/]*={0,2}$", s)) and len(s) % 4 == 0


class ContextCall(BaseModel):
    """
    ContextCall is a Pydantic model that represents a context to SiphonServer.
    Take an extension and base64 and it will process, returning the llm_context as a string.
    We can build on this, but for now, it is a simple model that takes a file path and processes it.
    """

    extension: str = Field(description="The extension to use for processing the file.")
    base64_data: str = Field(description="The base64 encoded content to process.")

    def model_post_init(self, __context):
        """
        Post-initialization processing to validate the extension and process the base64 data.
        """
        _ = __context
        if (
            self.extension
            not in extensions["audio"] + extensions["video"] + extensions["image"]
        ):
            raise ValueError(f"Extension '{self.extension}' is not supported.")
        if not is_base64_simple(self.base64_data):
            raise ValueError("Base64 data is not valid.")


def create_ContextCall_from_file(file_path: str | Path) -> ContextCall:
    """
    Create a ContextCall object from a file path.
    The file is read, encoded in base64, and the extension is extracted.
    """
    if not isinstance(file_path, Path):
        file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "rb") as f:
        file_data = f.read()

    base64_data = base64.b64encode(file_data).decode("utf-8")
    extension = file_path.suffix.lower()

    return ContextCall(extension=extension, base64_data=base64_data)
