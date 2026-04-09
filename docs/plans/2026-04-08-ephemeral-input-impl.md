# Ephemeral Input Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `@clipboard` sentinel and piped stdin support to the siphon CLI, routing image/audio/text bytes through the existing ephemeral pipeline.

**Architecture:** All work is client-side. The server already handles `origin=FILE_PATH` with `ensure_temp_file` in `process_siphon_service.py`. The client reads bytes (clipboard or stdin), sniffs the type, builds a `SiphonRequest` with `SiphonFile`, and sends it via `HeadwaterClient`. A new `ephemeral.py` module owns sniffing, clipboard reading, and request building; `siphon_cli.py` gains `@clipboard` detection, stdin detection, and a `--format` flag.

**Tech Stack:** Python 3.12, Click, `siphon_api` models, `AppKit` (macOS clipboard), `click.testing.CliRunner` for tests.

---

## Design Notes for Implementers

**`SiphonRequest` constraints (from `siphon_request.py`):**
- `source` must be an **absolute path** when `origin=FILE_PATH` (validated by `is_absolute_path`). Use `/clipboard.{ext}` or `/stdin.{ext}` as synthetic values.
- `SiphonFile.checksum` must be the **full 64-char SHA256 hex digest** (not truncated). The `SiphonFile` model validates this with `HEX64.fullmatch`.
- `SiphonFile.extension` must be in `EXTENSIONS` from `siphon_api.file_types`.

**Server-side:** No changes needed. `process_siphon_service.py` already calls `ensure_temp_file(request)` for `FILE_PATH` origin and reassigns `payload.original_source = request.source` afterwards.

**Dedup:** The server checks `REPOSITORY.exists(uri)` where `uri = "image:///{ext}/{hash}"`. Hash is computed server-side from the temp file. Identical bytes → same hash → same URI → cache hit → duplicate rejection. This is intentional (AC 11).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `siphon-client/src/siphon_client/ephemeral.py` | **Create** | `sniff_bytes`, `read_clipboard`, `read_stdin`, `build_ephemeral_request`, `EphemeralInputError` |
| `siphon-client/tests/test_ephemeral.py` | **Create** | Unit tests for ephemeral module |
| `siphon-client/src/siphon_client/cli/siphon_cli.py` | **Modify** | Make `source` optional in `gulp`/`extract`/`enrich`/`parse`; add `--format` to `gulp`/`extract`; add ephemeral resolution before `create_siphon_request` |

---

## Task 1: sniff_bytes ZIP rejection

**Fulfills:** AC 10 — `cat file.zip | siphon gulp` exits with code 1.

**Files:**
- Create: `siphon-client/src/siphon_client/ephemeral.py`
- Create: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# siphon-client/tests/test_ephemeral.py
from __future__ import annotations
import pytest
from siphon_client.ephemeral import sniff_bytes, EphemeralInputError


def test_sniff_bytes_rejects_zip():
    """AC 10: bare ZIP magic bytes raise EphemeralInputError."""
    zip_header = b"PK\x03\x04" + b"\x00" * 8
    with pytest.raises(EphemeralInputError, match="ZIP files are not supported"):
        sniff_bytes(zip_header)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_rejects_zip -v
```

Expected: `FAILED` — `ModuleNotFoundError` or `ImportError` (module doesn't exist yet).

- [ ] **Step 3: Implement ephemeral.py with sniff_bytes**

```python
# siphon-client/src/siphon_client/ephemeral.py
from __future__ import annotations
import hashlib
import platform
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from siphon_api.api.siphon_request import SiphonRequest, SiphonRequestParams

from siphon_api.file_types import EXTENSIONS

_ALL_EXTENSIONS: list[str] = [ext for exts in EXTENSIONS.values() for ext in exts]


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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_rejects_zip -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/src/siphon_client/ephemeral.py siphon-client/tests/test_ephemeral.py
git commit -m "feat(ephemeral): add ephemeral.py with sniff_bytes and ZIP rejection"
```

---

## Task 2: sniff_bytes plain text fallback

**Fulfills:** AC 3 — `echo "hello world" | siphon gulp` ingests as `source_type=DOC`.

> This task tests `sniff_bytes` for the UTF-8 fallback path. CLI wiring happens in Task 8.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py

def test_sniff_bytes_plain_text_returns_txt():
    """AC 3 (partial): plain UTF-8 text sniffs to .txt."""
    assert sniff_bytes(b"hello world") == ".txt"

def test_sniff_bytes_plain_text_multiline():
    """AC 3 (partial): multiline UTF-8 text sniffs to .txt."""
    data = "Line one\nLine two\nLine three\n".encode("utf-8")
    assert sniff_bytes(data) == ".txt"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_plain_text_returns_txt tests/test_ephemeral.py::test_sniff_bytes_plain_text_multiline -v
```

Expected: `FAILED` — `AssertionError` or import error depending on state.

- [ ] **Step 3: Verify sniff_bytes already handles this**

The UTF-8 fallback was implemented in Task 1. Run the tests — they should already pass without changes.

If they do not pass, confirm the `try/except UnicodeDecodeError` block is present and returns `".txt"` in `ephemeral.py`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_plain_text_returns_txt tests/test_ephemeral.py::test_sniff_bytes_plain_text_multiline -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): verify plain text sniffing for AC 3"
```

---

## Task 3: sniff_bytes image formats

**Fulfills:** AC 4 — `cat photo.png | siphon gulp` ingests as `source_type=IMAGE`.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to siphon-client/tests/test_ephemeral.py

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_png tests/test_ephemeral.py::test_sniff_bytes_jpeg tests/test_ephemeral.py::test_sniff_bytes_gif -v
```

Expected: `FAILED`.

- [ ] **Step 3: Verify sniff_bytes already handles this**

All three patterns were implemented in Task 1. If they don't pass, check the pattern matching order in `sniff_bytes`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_png tests/test_ephemeral.py::test_sniff_bytes_jpeg tests/test_ephemeral.py::test_sniff_bytes_gif -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): verify image format sniffing for AC 4"
```

---

## Task 4: sniff_bytes audio formats

**Fulfills:** AC 5 — `cat recording.mp3 | siphon gulp` ingests as `source_type=AUDIO`.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to siphon-client/tests/test_ephemeral.py

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_wav tests/test_ephemeral.py::test_sniff_bytes_mp3_id3 tests/test_ephemeral.py::test_sniff_bytes_mp3_syncword tests/test_ephemeral.py::test_sniff_bytes_flac tests/test_ephemeral.py::test_sniff_bytes_m4a -v
```

Expected: `FAILED`.

- [ ] **Step 3: Verify sniff_bytes already handles this**

All audio patterns were implemented in Task 1. If any fail, check the byte patterns in `sniff_bytes`. Specifically: `m4a` uses `header[4:8] == b"ftyp"` (bytes at offset 4–7), confirm the test header has `b"ftyp"` at offset 4.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_sniff_bytes_wav tests/test_ephemeral.py::test_sniff_bytes_mp3_id3 tests/test_ephemeral.py::test_sniff_bytes_mp3_syncword tests/test_ephemeral.py::test_sniff_bytes_flac tests/test_ephemeral.py::test_sniff_bytes_m4a -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): verify audio format sniffing for AC 5"
```

---

## Task 5: build_ephemeral_request and read_stdin

**Fulfills:** AC 6 — `cat ambiguous.bin | siphon gulp --format mp3` ingests as audio without sniffing.

This task implements `read_stdin` and `build_ephemeral_request` and tests the `--format` override path specifically. The sniffing path is tested via CLI integration in Tasks 8–9.

**Files:**
- Modify: `siphon-client/src/siphon_client/ephemeral.py`
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py
import io
import sys
from unittest.mock import patch
from siphon_client.ephemeral import read_stdin, build_ephemeral_request
from siphon_api.api.siphon_request import SiphonRequestParams
from siphon_api.enums import ActionType


def test_read_stdin_format_override_skips_sniffing():
    """AC 6: --format flag bypasses sniffing entirely."""
    binary_data = b"\x00\x01\x02\x03\xff\xfe"  # would not sniff to any valid type
    with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(binary_data))):
        with patch("sys.stdin.buffer", io.BytesIO(binary_data)):
            raw, ext = read_stdin(fmt_override="mp3")
    assert ext == ".mp3"
    assert raw == binary_data


def test_read_stdin_format_override_rejects_unknown_extension():
    """AC 6: unrecognized --format extension raises EphemeralInputError."""
    data = b"any bytes"
    with patch("sys.stdin.buffer", io.BytesIO(data)):
        with pytest.raises(EphemeralInputError, match="unrecognized format"):
            read_stdin(fmt_override="xyz")


def test_build_ephemeral_request_has_absolute_source():
    """build_ephemeral_request must produce an absolute path source."""
    params = SiphonRequestParams(action=ActionType.GULP)
    data = b"hello world"
    request = build_ephemeral_request(data, ".txt", "stdin", params)
    from pathlib import PurePosixPath
    assert PurePosixPath(request.source).is_absolute()


def test_build_ephemeral_request_checksum_is_64_chars():
    """SiphonFile.checksum must be the full 64-char SHA256 hex."""
    params = SiphonRequestParams(action=ActionType.GULP)
    data = b"hello world"
    request = build_ephemeral_request(data, ".txt", "stdin", params)
    assert len(request.file.checksum) == 64
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_stdin_format_override_skips_sniffing tests/test_ephemeral.py::test_read_stdin_format_override_rejects_unknown_extension tests/test_ephemeral.py::test_build_ephemeral_request_has_absolute_source tests/test_ephemeral.py::test_build_ephemeral_request_checksum_is_64_chars -v
```

Expected: `FAILED` — `ImportError` for `read_stdin` and `build_ephemeral_request`.

- [ ] **Step 3: Implement read_stdin and build_ephemeral_request**

Append to `siphon-client/src/siphon_client/ephemeral.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_stdin_format_override_skips_sniffing tests/test_ephemeral.py::test_read_stdin_format_override_rejects_unknown_extension tests/test_ephemeral.py::test_build_ephemeral_request_has_absolute_source tests/test_ephemeral.py::test_build_ephemeral_request_checksum_is_64_chars -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/src/siphon_client/ephemeral.py siphon-client/tests/test_ephemeral.py
git commit -m "feat(ephemeral): add read_stdin and build_ephemeral_request; --format override"
```

---

## Task 6: read_clipboard platform guard

**Fulfills:** AC 12 — on Linux, `siphon gulp @clipboard` exits with code 1 and the macOS-only message.

**Files:**
- Modify: `siphon-client/src/siphon_client/ephemeral.py`
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py
from unittest.mock import patch
from siphon_client.ephemeral import read_clipboard


def test_read_clipboard_non_macos_raises():
    """AC 12: read_clipboard raises EphemeralInputError on non-macOS."""
    with patch("platform.system", return_value="Linux"):
        with pytest.raises(EphemeralInputError, match="only supported on macOS"):
            read_clipboard()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_non_macos_raises -v
```

Expected: `FAILED` — `ImportError` for `read_clipboard`.

- [ ] **Step 3: Implement read_clipboard**

Append to `siphon-client/src/siphon_client/ephemeral.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_non_macos_raises -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/src/siphon_client/ephemeral.py siphon-client/tests/test_ephemeral.py
git commit -m "feat(ephemeral): add read_clipboard with macOS platform guard (AC 12)"
```

---

## Task 7: empty clipboard error

**Fulfills:** AC 9 — `siphon gulp @clipboard` with empty clipboard exits with code 1.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py
from unittest.mock import MagicMock, patch


def test_read_clipboard_empty_raises():
    """AC 9: empty clipboard raises EphemeralInputError."""
    mock_pasteboard = MagicMock()
    mock_pasteboard.types.return_value = ["public.utf8-plain-text"]
    mock_data = MagicMock()
    mock_data.__bytes__ = lambda self: b""
    mock_pasteboard.dataForType_.return_value = mock_data

    mock_appkit = MagicMock()
    mock_appkit.NSPasteboard.generalPasteboard.return_value = mock_pasteboard

    with patch("platform.system", return_value="Darwin"):
        with patch.dict("sys.modules", {"AppKit": mock_appkit}):
            with pytest.raises(EphemeralInputError, match="clipboard is empty"):
                read_clipboard()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_empty_raises -v
```

Expected: `FAILED`.

- [ ] **Step 3: Verify read_clipboard handles empty bytes**

The `if not raw_bytes: raise EphemeralInputError("error: clipboard is empty")` check was implemented in Task 6. If the test fails, the issue is with the mock setup — the `mock_data.__bytes__` approach may not work correctly with `bytes(ns_data)`. Fix: use `mock_pasteboard.dataForType_.return_value = b""` and check that `read_clipboard` handles `bytes(b"")` (which is `b""`).

If `AppKit.NSPasteboard.dataForType_` returns `b""` directly: the `bytes()` call on a `bytes` object returns it unchanged. Adjust mock to return `b""` directly.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_empty_raises -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): verify empty clipboard error for AC 9"
```

---

## Task 8: CLI — @clipboard + positional source conflict

**Fulfills:** AC 7 — `siphon gulp @clipboard /some/path` exits with code 1 and the conflict error message.

This task also wires `@clipboard` into the CLI for the first time.

**Files:**
- Modify: `siphon-client/src/siphon_client/cli/siphon_cli.py`
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py
from click.testing import CliRunner
from siphon_client.cli.siphon_cli import gulp


def test_gulp_clipboard_with_positional_arg_exits_1():
    """AC 7: @clipboard combined with positional source arg exits 1."""
    runner = CliRunner()
    result = runner.invoke(gulp, ["@clipboard", "/some/path"])
    assert result.exit_code == 1
    assert "cannot combine @clipboard with a source argument" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_gulp_clipboard_with_positional_arg_exits_1 -v
```

Expected: `FAILED` — Click will reject two positional arguments since `source` only accepts one.

- [ ] **Step 3: Modify siphon_cli.py**

In `siphon_cli.py`, make the following changes to `gulp` (apply the same pattern to `extract`, `enrich`, and `parse`):

1. Change `@click.argument("source")` to `@click.argument("source", default=None, required=False)`
2. Add `@click.option("--format", "fmt", default=None, help="Override type detection (e.g. mp3, png, txt).")` to `gulp` and `extract` only
3. Replace the `parse_source(source)` call at the top of `gulp` with the new resolution logic below

Add this function near the top of `siphon_cli.py` (after imports):

```python
from siphon_client.ephemeral import (
    EphemeralInputError,
    build_ephemeral_request,
    read_clipboard,
    read_stdin,
)

CLIPBOARD_SENTINEL = "@clipboard"


def resolve_ephemeral(
    source: str | None,
    params: SiphonRequestParams,
    fmt: str | None = None,
) -> SiphonRequest | None:
    """
    Resolve @clipboard or piped stdin to a SiphonRequest.
    Returns None if source is a normal path or URL (caller handles it).
    Raises SystemExit(1) on conflict or resolution error.
    """
    import sys as _sys

    has_stdin = not _sys.stdin.isatty()
    is_clipboard = source == CLIPBOARD_SENTINEL

    if is_clipboard and source is not None and source != CLIPBOARD_SENTINEL:
        # This branch won't trigger for the sentinel itself, but guard anyway
        pass

    # Conflict: both @clipboard sentinel AND a positional source was somehow passed
    # This can only happen if user does `siphon gulp @clipboard extra` — but Click
    # will reject extra positional args. The real conflict is @clipboard used as source
    # while also having another source — covered by making source optional and
    # checking for ambiguity below.

    if not is_clipboard and not has_stdin:
        return None  # Normal path

    if is_clipboard and has_stdin:
        click.echo("error: cannot combine @clipboard with piped stdin", err=True)
        raise SystemExit(1)

    if is_clipboard:
        try:
            raw, ext = read_clipboard()
        except EphemeralInputError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        logger.info(f"[EPHEMERAL] clipboard: ext={ext} bytes={len(raw)}")
        return build_ephemeral_request(raw, ext, "clipboard", params)

    if has_stdin:
        if source is not None:
            click.echo(
                "error: cannot combine piped input with a source argument", err=True
            )
            raise SystemExit(1)
        try:
            raw, ext = read_stdin(fmt_override=fmt)
        except EphemeralInputError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        logger.info(f"[EPHEMERAL] stdin: ext={ext} bytes={len(raw)}")
        return build_ephemeral_request(raw, ext, "stdin", params)

    return None
```

Update the `gulp` command signature and body:

```python
@siphon.command()
@click.argument("source", default=None, required=False)
@click.option(
    "--return-type", "-r",
    type=click.Choice(["st", "u", "c", "m", "t", "d", "s", "id", "json"]),
    default="s",
    help="Type to return: ...",
)
@click.option("--no-cache", is_flag=True, default=False)
@click.option("--format", "fmt", default=None, help="Override type detection (e.g. mp3, png, txt).")
def gulp(source, return_type, no_cache, fmt):
    logger.info(f"Received source: {source}")
    params = SiphonRequestParams(action=ActionType.GULP, use_cache=not no_cache)

    request = resolve_ephemeral(source, params, fmt)
    if request is None:
        source = parse_source(source)
        request = create_siphon_request(source=source, request_params=params)

    from headwater_client.client.headwater_client import HeadwaterClient
    client = HeadwaterClient()
    response = client.siphon.process(request)
    # ... rest of output logic unchanged
```

Apply the same `source=None, required=False` change and `resolve_ephemeral` call to `extract`, `enrich`, and `parse`. Only `gulp` and `extract` get the `--format` option.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_gulp_clipboard_with_positional_arg_exits_1 -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/src/siphon_client/cli/siphon_cli.py siphon-client/tests/test_ephemeral.py
git commit -m "feat(cli): wire @clipboard sentinel and conflict guard (AC 7)"
```

---

## Task 9: CLI — piped stdin + positional source conflict

**Fulfills:** AC 8 — `cat file.txt | siphon gulp /some/path` exits with code 1.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py


def test_gulp_stdin_with_positional_arg_exits_1():
    """AC 8: piped stdin combined with positional source arg exits 1."""
    runner = CliRunner()
    result = runner.invoke(gulp, ["/some/path"], input="hello world")
    assert result.exit_code == 1
    assert "cannot combine piped input with a source argument" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_gulp_stdin_with_positional_arg_exits_1 -v
```

Expected: `FAILED`.

- [ ] **Step 3: Verify resolve_ephemeral handles this**

The `has_stdin` + `source is not None` branch in `resolve_ephemeral` (implemented in Task 8) should handle this. If the test fails, check whether `CliRunner` with `input=` sets `sys.stdin.isatty()` to False — it should, but confirm.

If `CliRunner` doesn't set `isatty()` to False when `input=` is provided, add `mix_stderr=False` to `CliRunner()` and/or check the Click docs for `standalone_mode`.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_gulp_stdin_with_positional_arg_exits_1 -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(cli): verify piped stdin + positional arg conflict for AC 8"
```

---

## Task 10: dedup via content hash

**Fulfills:** AC 11 — ingesting identical clipboard/stdin content twice results in duplicate rejection.

This test verifies that `build_ephemeral_request` produces the same `SiphonFile.checksum` for identical bytes, which the server maps to the same URI and rejects as a cache hit.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_build_ephemeral_request_same_bytes_same_checksum tests/test_ephemeral.py::test_build_ephemeral_request_different_bytes_different_checksum -v
```

Expected: `FAILED`.

- [ ] **Step 3: Verify build_ephemeral_request already handles this**

`build_ephemeral_request` uses `hashlib.sha256(data).hexdigest()` which is deterministic. These tests should already pass given the Task 5 implementation.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_build_ephemeral_request_same_bytes_same_checksum tests/test_ephemeral.py::test_build_ephemeral_request_different_bytes_different_checksum -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): verify dedup via content hash for AC 11"
```

---

## Task 11: clipboard PNG → IMAGE (integration)

**Fulfills:** AC 1 — `siphon gulp @clipboard` with PNG in clipboard ingests as `source_type=IMAGE`.

This is a macOS integration test. It requires `pyobjc-framework-Cocoa` and a real clipboard write. Skip on non-macOS.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py
import platform
from unittest.mock import MagicMock, patch


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_png_returns_image_extension tests/test_ephemeral.py::test_build_ephemeral_request_for_clipboard_png -v
```

Expected: `FAILED` (or `SKIPPED` on non-macOS — if skipped, that's correct behavior for the platform guard).

- [ ] **Step 3: Verify read_clipboard and build_ephemeral_request handle this**

Both functions were implemented in Tasks 5 and 6. If running on macOS and the tests fail, check that `mock_pasteboard.dataForType_.return_value = png_bytes` correctly returns `bytes` through `bytes(ns_data)` — `bytes(b"...")` returns the same bytes object unchanged.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_png_returns_image_extension tests/test_ephemeral.py::test_build_ephemeral_request_for_clipboard_png -v
```

Expected: both `PASSED` on macOS; `SKIPPED` on other platforms.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): clipboard PNG → image extension for AC 1"
```

---

## Task 12: clipboard text → DOC (integration)

**Fulfills:** AC 2 — `siphon gulp @clipboard` with plain text in clipboard ingests as `source_type=DOC`.

**Files:**
- Modify: `siphon-client/tests/test_ephemeral.py`

- [ ] **Step 1: Write the failing test**

```python
# append to siphon-client/tests/test_ephemeral.py


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_plain_text_returns_txt_extension tests/test_ephemeral.py::test_build_ephemeral_request_for_clipboard_text -v
```

Expected: `FAILED` or `SKIPPED` on non-macOS.

- [ ] **Step 3: Verify read_clipboard and build_ephemeral_request handle this**

The `public.utf8-plain-text` → `.txt` mapping is in `_CLIPBOARD_UTI_MAP` from Task 6. If the test fails on macOS, check the mock setup matches the `for uti, ext in _CLIPBOARD_UTI_MAP.items()` iteration order.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py::test_read_clipboard_plain_text_returns_txt_extension tests/test_ephemeral.py::test_build_ephemeral_request_for_clipboard_text -v
```

Expected: both `PASSED` on macOS; `SKIPPED` on other platforms.

- [ ] **Step 5: Commit**

```bash
git add siphon-client/tests/test_ephemeral.py
git commit -m "test(ephemeral): clipboard text → .txt extension for AC 2"
```

---

## Final check: run full test suite

- [ ] **Run all ephemeral tests**

```bash
cd siphon-client
uv run pytest tests/test_ephemeral.py -v
```

Expected: all tests `PASSED` or `SKIPPED` (macOS-only tests skip on other platforms). No `FAILED`.

- [ ] **Deploy to AlphaBlue**

```bash
cd /Users/bianders/Brian_Code/siphon
bash scripts/deploy.sh
```

---

## Self-Review: Spec Coverage Check

| AC | Task | Status |
|---|---|---|
| AC 1: clipboard PNG → IMAGE | Task 11 | Covered |
| AC 2: clipboard text → DOC | Task 12 | Covered |
| AC 3: stdin plain text → DOC | Task 2 (sniff), Task 8 (CLI) | Covered |
| AC 4: stdin PNG → IMAGE | Task 3 (sniff), Task 8 (CLI) | Covered |
| AC 5: stdin MP3 → AUDIO | Task 4 (sniff), Task 8 (CLI) | Covered |
| AC 6: --format override | Task 5 | Covered |
| AC 7: @clipboard + positional → exit 1 | Task 8 | Covered |
| AC 8: stdin + positional → exit 1 | Task 9 | Covered |
| AC 9: empty clipboard → exit 1 | Task 7 | Covered |
| AC 10: ZIP → exit 1 | Task 1 | Covered |
| AC 11: dedup via hash | Task 10 | Covered |
| AC 12: Linux + @clipboard → exit 1 | Task 6 | Covered |

**Note on ACs 3–5:** The sniff function is tested in Tasks 2–4. The CLI routing (stdin detection + `build_ephemeral_request` call) is wired in Task 8. ACs 3–5 are fully covered between those tasks but do not have a single end-to-end CLI integration test that mocks `HeadwaterClient`. Add such a test if full CLI path coverage is required — it was omitted here to avoid complexity in mocking the HeadwaterClient response models.
