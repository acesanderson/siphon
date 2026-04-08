from __future__ import annotations
import pytest
from siphon_client.ephemeral import sniff_bytes, EphemeralInputError


def test_sniff_bytes_rejects_zip():
    """AC 10: bare ZIP magic bytes raise EphemeralInputError."""
    zip_header = b"PK\x03\x04" + b"\x00" * 8
    with pytest.raises(EphemeralInputError, match="ZIP files are not supported"):
        sniff_bytes(zip_header)


def test_sniff_bytes_plain_text_returns_txt():
    """AC 3 (partial): plain UTF-8 text sniffs to .txt."""
    assert sniff_bytes(b"hello world") == ".txt"


def test_sniff_bytes_plain_text_multiline():
    """AC 3 (partial): multiline UTF-8 text sniffs to .txt."""
    data = "Line one\nLine two\nLine three\n".encode("utf-8")
    assert sniff_bytes(data) == ".txt"


def test_sniff_bytes_png():
    """AC 4 (partial): PNG magic bytes sniff to .png."""
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4
    assert sniff_bytes(png_header) == ".png"


def test_sniff_bytes_jpeg():
    """AC 4 (partial): JPEG magic bytes sniff to .jpg."""
    jpeg_header = b"\xff\xd8\xff" + b"\x00" * 9
    assert sniff_bytes(jpeg_header) == ".jpg"


def test_sniff_bytes_gif():
    """AC 4 (partial): GIF magic bytes sniff to .gif."""
    gif_header = b"GIF8" + b"\x00" * 8
    assert sniff_bytes(gif_header) == ".gif"
