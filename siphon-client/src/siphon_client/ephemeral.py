from __future__ import annotations
import hashlib
import platform
import sys


class EphemeralInputError(ValueError):
    """Raised when ephemeral input cannot be resolved."""


def sniff_bytes(data: bytes) -> str:
    """
    Inspect up to the first 12 bytes to determine file extension.
    Falls back to UTF-8 decode attempt for plain text.
    Returns an extension like '.png', '.mp3', '.txt'.
    Raises EphemeralInputError if type cannot be determined.
    """
    header = data[:12]

    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if header[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if header[:4] == b"GIF8":
        return ".gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return ".wav"
    if header[:3] == b"ID3" or header[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return ".mp3"
    if header[:4] == b"fLaC":
        return ".flac"
    if header[4:8] == b"ftyp":
        return ".m4a"
    if header[:4] == b"%PDF":
        return ".pdf"
    if header[:4] == b"PK\x03\x04":
        raise EphemeralInputError(
            "error: ZIP files are not supported; "
            "if this is a DOCX, use --format docx"
        )
    try:
        data.decode("utf-8")
        return ".txt"
    except UnicodeDecodeError:
        raise EphemeralInputError(
            "error: could not determine input type; use --format to specify"
        )
