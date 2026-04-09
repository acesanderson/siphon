from __future__ import annotations
from typing import TYPE_CHECKING
import hashlib
import platform
import sys

from siphon_api.file_types import EXTENSIONS

if TYPE_CHECKING:
    from siphon_api.api.siphon_request import SiphonRequest, SiphonRequestParams


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


_ALL_EXTENSIONS: list[str] = [ext for exts in EXTENSIONS.values() for ext in exts]


def read_stdin(fmt_override: str | None = None) -> tuple[bytes, str]:
    """
    Read all stdin bytes. Use fmt_override to skip sniffing.
    Returns (raw_bytes, extension) where extension includes the leading dot.
    Raises EphemeralInputError on empty input or unrecognized format.
    """
    data = sys.stdin.buffer.read()
    if not data:
        raise EphemeralInputError("error: stdin is empty")

    if fmt_override is not None:
        ext = fmt_override if fmt_override.startswith(".") else f".{fmt_override}"
        if ext not in _ALL_EXTENSIONS:
            valid = ", ".join(sorted(_ALL_EXTENSIONS))
            raise EphemeralInputError(
                f"error: unrecognized format '{ext}'; valid extensions: {valid}"
            )
        return data, ext

    return data, sniff_bytes(data)


_CLIPBOARD_UTI_MAP: dict[str, str] = {
    "public.png": ".png",
    "public.jpeg": ".jpg",
    "public.gif": ".gif",
    "public.tiff": ".tiff",
    "public.webp": ".webp",
    "public.utf8-plain-text": ".txt",
}


def read_clipboard() -> tuple[bytes, str]:
    """
    Read clipboard content on macOS.
    Returns (raw_bytes, extension).
    Raises EphemeralInputError for unsupported types, empty clipboard, or non-macOS.
    """
    if platform.system() != "Darwin":
        raise EphemeralInputError(
            "error: @clipboard is only supported on macOS"
        )

    import AppKit  # available only on macOS via pyobjc-framework-Cocoa

    pasteboard = AppKit.NSPasteboard.generalPasteboard()
    types = list(pasteboard.types() or [])

    for uti, ext in _CLIPBOARD_UTI_MAP.items():
        if uti in types:
            ns_data = pasteboard.dataForType_(uti)
            if ns_data is None:
                continue
            raw_bytes = bytes(ns_data)
            if not raw_bytes:
                raise EphemeralInputError("error: clipboard is empty")
            return raw_bytes, ext

    found = types[0] if types else "unknown"
    raise EphemeralInputError(
        f"error: unsupported clipboard type '{found}'; "
        "supported: image, plain text"
    )


def build_ephemeral_request(
    data: bytes,
    ext: str,
    source_prefix: str,
    params: SiphonRequestParams,
) -> SiphonRequest:
    """
    Build a SiphonRequest from raw bytes for ephemeral (clipboard/stdin) input.

    source_prefix: "clipboard" or "stdin"
    ext: file extension including leading dot (e.g. ".png", ".txt")
    """
    from siphon_api.api.siphon_request import SiphonFile, SiphonRequest
    from siphon_api.enums import SourceOrigin

    normalized = ext if ext.startswith(".") else f".{ext}"
    checksum = hashlib.sha256(data).hexdigest()  # full 64-char hex
    source = f"/{source_prefix}{normalized}"     # absolute synthetic path

    siphon_file = SiphonFile(
        data=data,
        checksum=checksum,
        extension=normalized,
    )
    return SiphonRequest(
        source=source,
        origin=SourceOrigin.FILE_PATH,
        params=params,
        file=siphon_file,
    )
