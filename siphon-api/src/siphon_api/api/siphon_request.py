from siphon_api.enums import SourceOrigin, ActionType
from siphon_api.file_types import EXTENSIONS
from pydantic import (
    BaseModel,
    Field,
    model_validator,
    field_validator,
    field_serializer,
)
from urllib.parse import urlparse
from pathlib import PurePosixPath
from typing import Literal
import base64
import hashlib
import hmac
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def is_absolute_path(p: str) -> bool:
    """Cross-platform absolute path format check, no FS access."""
    if PurePosixPath(p).is_absolute():
        return True
    # Windows drive letter or UNC path
    return bool(re.match(r"^(?:[a-zA-Z]:\\|\\\\)", p))


class SiphonRequestParams(BaseModel):
    action: ActionType = Field(
        ...,
        description="Action to perform on the source.",
    )
    use_cache: bool = Field(
        default=True,
        description="Whether caching is enabled for this request.",
    )
    diarize: bool = Field(
        default=False,
        description="Whether to run speaker diarization (audio sources only).",
    )


class SiphonFile(BaseModel):
    data: bytes = Field(
        ..., description="Raw file bytes; JSON transport may be base64."
    )
    checksum: str = Field(..., description="SHA256 hex digest of raw bytes.")
    extension: str = Field(..., description="File extension, e.g., '.pdf', '.txt'.")

    @field_validator("data", mode="before")
    @classmethod
    def decode_base64_if_needed(cls, v):
        if isinstance(v, (bytes, bytearray)):
            # If we're given bytes, just use them (from create_siphon_request)
            return bytes(v)
        if isinstance(v, str):
            # If we're given a str, it's from JSON and needs decoding
            return base64.b64decode(v, validate=True)
        raise TypeError("data must be bytes or base64 string")

    # ADD this serializer (for JSON serialization)
    @field_serializer("data")
    def serialize_data_as_base64(self, v: bytes) -> str:
        """Serializes raw bytes to a base64-encoded string for JSON."""
        return base64.b64encode(v).decode("utf-8")

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, v: str) -> str:
        v = v.lower()
        if not HEX64.fullmatch(v):
            raise ValueError("checksum must be a 64-character hex SHA256 digest")
        return v

    @field_validator("extension")
    @classmethod
    def normalize_extension(cls, v: str) -> str:
        ext = v.lower().strip()
        if not ext.startswith("."):
            ext = "." + ext
        if not any(ext in exts for exts in EXTENSIONS.values()):
            raise ValueError(f"Unsupported file extension: {v}")
        return ext

    @model_validator(mode="after")
    def check_digest(self):
        computed = hashlib.sha256(self.data).hexdigest()
        if not hmac.compare_digest(computed, self.checksum):
            raise ValueError(
                f"Checksum mismatch: expected {self.checksum}, got {computed}"
            )
        return self


class SiphonRequest(BaseModel):
    source: str = Field(
        ...,
        description="Source string — absolute file path or URL, depending on origin.",
    )
    origin: SourceOrigin = Field(..., description="Either URL or FILE_PATH.")
    params: SiphonRequestParams = Field(
        ..., description="Parameters for the siphon request."
    )

    # Optional file payload for FILE_PATH origin
    file: SiphonFile | None = Field(
        default=None,
        description="File bytes and metadata; required for FILE_PATH origin.",
    )

    @model_validator(mode="after")
    def validate_consistency(self):
        if self.origin == SourceOrigin.FILE_PATH:
            # Require absolute path (format only) and file payload
            if not is_absolute_path(self.source):
                raise ValueError(
                    "source must be an absolute path when origin=FILE_PATH"
                )
            if self.file is None:
                raise ValueError("file content must be provided for FILE_PATH origin.")
        elif self.origin == SourceOrigin.URL:
            # Require valid URL and no file payload
            if self.file is not None:
                raise ValueError("file content should not be provided for URL origin.")
            parsed = urlparse(self.source)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("source must be a valid http(s) URL when origin=URL.")
        else:
            raise ValueError(f"Unsupported origin type: {self.origin}")
        return self
