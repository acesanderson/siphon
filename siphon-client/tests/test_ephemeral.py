from __future__ import annotations
import io
import platform
import pytest
from unittest.mock import patch, MagicMock
from siphon_client.ephemeral import sniff_bytes, EphemeralInputError, read_stdin, build_ephemeral_request, read_clipboard
from siphon_api.api.siphon_request import SiphonRequestParams
from siphon_api.enums import ActionType


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


def test_sniff_bytes_wav():
    """AC 5 (partial): WAV magic bytes sniff to .wav."""
    wav_header = b"RIFF" + b"\x00" * 4 + b"WAVE"
    assert sniff_bytes(wav_header) == ".wav"


def test_sniff_bytes_mp3_id3():
    """AC 5 (partial): MP3 with ID3 tag sniffs to .mp3."""
    mp3_header = b"ID3" + b"\x00" * 9
    assert sniff_bytes(mp3_header) == ".mp3"


def test_sniff_bytes_mp3_syncword():
    """AC 5 (partial): MP3 with sync word sniffs to .mp3."""
    mp3_header = b"\xff\xfb" + b"\x00" * 10
    assert sniff_bytes(mp3_header) == ".mp3"


def test_sniff_bytes_flac():
    """AC 5 (partial): FLAC magic bytes sniff to .flac."""
    flac_header = b"fLaC" + b"\x00" * 8
    assert sniff_bytes(flac_header) == ".flac"


def test_sniff_bytes_m4a():
    """AC 5 (partial): M4A ftyp box sniffs to .m4a."""
    m4a_header = b"\x00\x00\x00\x20" + b"ftyp" + b"\x00" * 4
    assert sniff_bytes(m4a_header) == ".m4a"


def test_read_stdin_format_override_skips_sniffing():
    """AC 6: --format flag bypasses sniffing entirely."""
    binary_data = b"\x00\x01\x02\x03\xff\xfe"  # would not sniff to any valid type
    with patch("siphon_client.ephemeral.sys") as mock_sys:
        mock_sys.stdin.buffer.read.return_value = binary_data
        raw, ext = read_stdin(fmt_override="mp3")
    assert ext == ".mp3"
    assert raw == binary_data


def test_read_stdin_format_override_rejects_unknown_extension():
    """AC 6: unrecognized --format extension raises EphemeralInputError."""
    data = b"any bytes"
    with patch("siphon_client.ephemeral.sys") as mock_sys:
        mock_sys.stdin.buffer.read.return_value = data
        with pytest.raises(EphemeralInputError, match="unrecognized format"):
            read_stdin(fmt_override="xyz")


def test_build_ephemeral_request_has_absolute_source():
    """build_ephemeral_request must produce an absolute path source."""
    from pathlib import PurePosixPath
    params = SiphonRequestParams(action=ActionType.GULP)
    data = b"hello world"
    request = build_ephemeral_request(data, ".txt", "stdin", params)
    assert PurePosixPath(request.source).is_absolute()


def test_build_ephemeral_request_checksum_is_64_chars():
    """SiphonFile.checksum must be the full 64-char SHA256 hex."""
    params = SiphonRequestParams(action=ActionType.GULP)
    data = b"hello world"
    request = build_ephemeral_request(data, ".txt", "stdin", params)
    assert len(request.file.checksum) == 64


def test_read_clipboard_non_macos_raises():
    """AC 12: read_clipboard raises EphemeralInputError on non-macOS."""
    with patch("siphon_client.ephemeral.platform.system", return_value="Linux"):
        with pytest.raises(EphemeralInputError, match="only supported on macOS"):
            read_clipboard()


def test_read_clipboard_empty_raises():
    """AC 9: empty clipboard raises EphemeralInputError."""
    mock_pasteboard = MagicMock()
    mock_pasteboard.types.return_value = ["public.utf8-plain-text"]
    mock_pasteboard.dataForType_.return_value = b""

    mock_appkit = MagicMock()
    mock_appkit.NSPasteboard.generalPasteboard.return_value = mock_pasteboard

    with patch("siphon_client.ephemeral.platform.system", return_value="Darwin"):
        with patch.dict("sys.modules", {"AppKit": mock_appkit}):
            with pytest.raises(EphemeralInputError, match="clipboard is empty"):
                read_clipboard()


from click.testing import CliRunner
from siphon_client.cli.siphon_cli import gulp


def test_gulp_clipboard_with_positional_arg_exits_1():
    """AC 7: @clipboard combined with positional source arg exits 1."""
    runner = CliRunner()
    result = runner.invoke(gulp, ["@clipboard", "/some/path"])
    assert result.exit_code == 1
    assert "cannot combine @clipboard with a source argument" in result.output


def test_gulp_stdin_with_positional_arg_exits_1():
    """AC 8: piped stdin combined with positional source arg exits 1."""
    runner = CliRunner()
    result = runner.invoke(gulp, ["/some/path"], input="hello world")
    assert result.exit_code == 1
    assert "cannot combine piped input with a source argument" in result.output


def test_build_ephemeral_request_same_bytes_same_checksum():
    """AC 11: identical bytes produce identical checksum (same URI → dedup)."""
    params = SiphonRequestParams(action=ActionType.GULP)
    data = b"duplicate content"
    req1 = build_ephemeral_request(data, ".txt", "stdin", params)
    req2 = build_ephemeral_request(data, ".txt", "stdin", params)
    assert req1.file.checksum == req2.file.checksum


def test_build_ephemeral_request_different_bytes_different_checksum():
    """AC 11 (inverse): different bytes produce different checksum."""
    params = SiphonRequestParams(action=ActionType.GULP)
    req1 = build_ephemeral_request(b"content a", ".txt", "stdin", params)
    req2 = build_ephemeral_request(b"content b", ".txt", "stdin", params)
    assert req1.file.checksum != req2.file.checksum


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_read_clipboard_png_returns_image_extension():
    """AC 1 (partial): clipboard with PNG UTI returns .png extension."""
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    mock_pasteboard = MagicMock()
    mock_pasteboard.types.return_value = ["public.png"]
    mock_pasteboard.dataForType_.return_value = png_bytes

    mock_appkit = MagicMock()
    mock_appkit.NSPasteboard.generalPasteboard.return_value = mock_pasteboard

    with patch.dict("sys.modules", {"AppKit": mock_appkit}):
        raw, ext = read_clipboard()

    assert ext == ".png"
    assert raw == png_bytes


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_build_ephemeral_request_for_clipboard_png():
    """AC 1: clipboard PNG bytes produce FILE_PATH request with image extension."""
    from siphon_api.enums import SourceOrigin
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    params = SiphonRequestParams(action=ActionType.GULP)
    request = build_ephemeral_request(png_bytes, ".png", "clipboard", params)
    assert request.origin == SourceOrigin.FILE_PATH
    assert request.source == "/clipboard.png"
    assert request.file.extension == ".png"


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_read_clipboard_plain_text_returns_txt_extension():
    """AC 2 (partial): clipboard with plain text UTI returns .txt extension."""
    text_bytes = "Hello, siphon!".encode("utf-8")

    mock_pasteboard = MagicMock()
    mock_pasteboard.types.return_value = ["public.utf8-plain-text"]
    mock_pasteboard.dataForType_.return_value = text_bytes

    mock_appkit = MagicMock()
    mock_appkit.NSPasteboard.generalPasteboard.return_value = mock_pasteboard

    with patch.dict("sys.modules", {"AppKit": mock_appkit}):
        raw, ext = read_clipboard()

    assert ext == ".txt"
    assert raw == text_bytes


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_build_ephemeral_request_for_clipboard_text():
    """AC 2: clipboard text bytes produce FILE_PATH request with .txt extension."""
    from siphon_api.enums import SourceOrigin
    text_bytes = "Hello, siphon!".encode("utf-8")
    params = SiphonRequestParams(action=ActionType.GULP)
    request = build_ephemeral_request(text_bytes, ".txt", "clipboard", params)
    assert request.origin == SourceOrigin.FILE_PATH
    assert request.source == "/clipboard.txt"
    assert request.file.extension == ".txt"
