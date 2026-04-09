# Ephemeral Input Support

**Date:** 2026-04-08

## Problem

The siphon pipeline assumes all sources exist on disk at parse and extraction time. Parsers call `Path(source).exists()`, extractors call `Path(source).read_bytes()`, and the `source` field of `SiphonRequest` is always a path string or URL. Raw bytes carried in `SiphonRequest.file` are never used.

This blocks two natural input patterns: the `@clipboard` sentinel and piped stdin.

---

## Interface

### `@clipboard` sentinel

```
siphon gulp @clipboard
siphon extract @clipboard
siphon gulp @clipboard --format png   # override sniffed type
```

`@clipboard` is a reserved sentinel value for the `source` positional argument. It is resolved entirely client-side before `SiphonRequest` is constructed. The CLI reads clipboard content, detects type, and constructs the request with bytes in `SiphonRequest.file`.

The `source` field in the resulting `SiphonRequest` is set to a synthetic name of the form `clipboard.{ext}` (e.g. `clipboard.png`, `clipboard.txt`). This value is stored as `original_source` in `SourceInfo`. It is intentionally non-unique — dedup is based on content hash, not source name.

`@clipboard` is macOS-only. No Windows or Linux clipboard support is in scope.

### Piped stdin (auto-detected)

```
cat notes.txt | siphon gulp
cat recording.mp3 | siphon gulp
cat photo.png | siphon gulp
cat ambiguous.bin | siphon gulp --format mp3   # override sniffed type
```

Detected via `not sys.stdin.isatty()`. The `source` positional argument is omitted; passing one alongside piped stdin is an error (see Failure Modes). CLI reads stdin fully into memory, sniffs type, and routes accordingly.

The `source` field in `SiphonRequest` is set to `stdin.{ext}`.

`@stdin` is not a supported sentinel — stdin detection is always implicit.

---

## Type Detection

### `--format` flag

Both `@clipboard` and stdin accept an optional `--format {ext}` flag (e.g. `--format mp3`, `--format png`) that bypasses sniffing entirely. The extension must be a value in `EXTENSIONS` from `siphon_api.file_types`. If an unrecognized extension is given, exit with code 1 and list valid values.

### Clipboard (macOS)

Read the clipboard UTI (Uniform Type Identifier) directly — do not sniff bytes:

| UTI | Extension | Source type |
|---|---|---|
| `public.png` | `.png` | Image |
| `public.jpeg` | `.jpg` | Image |
| `public.gif` | `.gif` | Image |
| `public.tiff` | `.tiff` | Image |
| `public.webp` | `.webp` | Image |
| `public.utf8-plain-text` | `.txt` | Doc |

Any other UTI is an error (see Failure Modes). HTML, spreadsheet, and file-reference clipboard types are not supported.

### Stdin binary sniffing

Read exactly the first 12 bytes. Check patterns in the order listed (earlier rows take priority):

| Magic bytes | Offset | Format | Extension | Source type |
|---|---|---|---|---|
| `\x89PNG\r\n\x1a\n` | 0 | PNG | `.png` | Image |
| `\xff\xd8\xff` | 0 | JPEG | `.jpg` | Image |
| `GIF8` | 0 | GIF | `.gif` | Image |
| `RIFF` + `WAVE` at offset 8 | 0, 8 | WAV | `.wav` | Audio |
| `ID3` | 0 | MP3 | `.mp3` | Audio |
| `\xff\xfb` or `\xff\xf3` | 0 | MP3 | `.mp3` | Audio |
| `fLaC` | 0 | FLAC | `.flac` | Audio |
| `....ftyp` | 4 | M4A | `.m4a` | Audio |
| `%PDF` | 0 | PDF | `.pdf` | Doc |
| `PK\x03\x04` + filename ends in `.docx` | 0 | DOCX | `.docx` | Doc |

If no pattern matches: attempt to decode the **full** stdin buffer as UTF-8 (`bytes.decode('utf-8')`). If it succeeds, treat as `.txt` / Doc. If it raises `UnicodeDecodeError`, exit with code 1 and print: `error: could not determine input type; use --format to specify`.

Note: `PK\x03\x04` alone does not route to Doc — it must be confirmed as DOCX. A bare ZIP is an error.

---

## Source Type Routing

| Input | Ext | Source type | URI |
|---|---|---|---|
| Clipboard image | `.png` / `.jpg` / etc. | Image | `image:///{ext}/{hash}` |
| Clipboard text | `.txt` | Doc | `doc:///txt/{hash}` |
| Stdin image | `.png` / `.jpg` / etc. | Image | `image:///{ext}/{hash}` |
| Stdin audio | `.mp3` / `.wav` / etc. | Audio | `audio:///{ext}/{hash}` |
| Stdin doc/text | `.pdf` / `.docx` / `.txt` | Doc | `doc:///{ext}/{hash}` |

Hash is SHA-256 of the full raw bytes, truncated to 16 hex chars, computed client-side. This is sent as `SiphonFile.checksum`. Server-side parsers that recompute hash from the temp file must produce the same value — if they diverge, this is a bug.

Identical content submitted twice (same bytes) produces the same hash and is treated as a duplicate by the normal dedup path. This is intentional.

---

## Server-Side Fix

`ensure_temp_file()` exists in `siphon_api` but is never called in the pipeline. The fix is one integration point in the server's pipeline entry function (wherever `SiphonPipeline.process(source)` is called from the request handler):

```python
# Pseudocode — exact location: server request handler, before pipeline.process()
if request.origin == SourceOrigin.FILE_PATH and not Path(request.source).exists():
    with ensure_temp_file(request.file.data, request.file.extension) as tmp_path:
        result = pipeline.process(str(tmp_path), ...)
else:
    result = pipeline.process(request.source, ...)
```

The temp file must be cleaned up in all cases — use a context manager (`with` block) so cleanup is guaranteed on both success and exception. Do not delete-then-recreate; let the context manager handle it.

No changes are required to parsers, extractors, or enrichers.

---

## Client-Side Changes

- Detect `@clipboard` before normal source resolution. If another positional argument is also provided, exit with code 1.
- Detect `not sys.stdin.isatty()`. If a source positional argument is also provided, exit with code 1.
- Sniffing and clipboard reading live in `siphon_client/ephemeral.py`. Export two functions: `read_clipboard() -> tuple[bytes, str]` and `read_stdin(fmt_override: str | None) -> tuple[bytes, str]`, both returning `(raw_bytes, extension)`.
- Construct `SiphonFile(data=raw_bytes, checksum=sha256(raw_bytes)[:16], extension=ext)` and `origin=SourceOrigin.FILE_PATH` with `source=f"clipboard.{ext}"` or `source=f"stdin.{ext}"`.

---

## Failure Modes

| Condition | Behavior |
|---|---|
| `@clipboard` with empty clipboard | Exit code 1: `error: clipboard is empty` |
| `@clipboard` with unsupported UTI (HTML, spreadsheet, etc.) | Exit code 1: `error: unsupported clipboard type '{uti}'; supported: image, plain text` |
| `@clipboard` on non-macOS | Exit code 1: `error: @clipboard is only supported on macOS` |
| `@clipboard` + positional source arg | Exit code 1: `error: cannot combine @clipboard with a source argument` |
| Piped stdin + positional source arg | Exit code 1: `error: cannot combine piped input with a source argument` |
| Stdin sniffing fails and not valid UTF-8 | Exit code 1: `error: could not determine input type; use --format to specify` |
| `--format` given with unrecognized extension | Exit code 1: list valid extensions from `EXTENSIONS` |
| Temp file write fails (disk full, permissions) | Propagate OS error; do not swallow |
| `PK\x03\x04` magic but not DOCX | Exit code 1: `error: ZIP files are not supported; if this is a DOCX, use --format docx` |
| Pipeline exception during temp file usage | Temp file cleaned up via context manager; exception propagates normally |

No size limit is enforced in this implementation. If one is needed, it is a separate concern.

---

## Non-Goals

- Windows or Linux clipboard support
- Streaming stdin (full buffer read required before processing)
- `@selection`, `@screenshot`, or any other sentinels
- Multi-item clipboard (e.g., multiple files copied at once)
- Inferring content type from filename when `--format` is used (extension is taken as given)
- Dedup suppression for clipboard inputs (same content twice = same hash = rejected; intentional)
- Temp file path preservation in `original_source` (synthetic names only)

---

## Acceptance Criteria

1. `siphon gulp @clipboard` with a PNG image in clipboard ingests successfully; record appears in DB with `source_type=IMAGE` and `uri` matching `image:///png/{hash}`.
2. `siphon gulp @clipboard` with plain text in clipboard ingests successfully; record appears with `source_type=DOC` and `uri` matching `doc:///txt/{hash}`.
3. `echo "hello world" | siphon gulp` ingests successfully as `source_type=DOC`.
4. `cat photo.png | siphon gulp` ingests successfully as `source_type=IMAGE`.
5. `cat recording.mp3 | siphon gulp` ingests successfully as `source_type=AUDIO`.
6. `cat ambiguous.bin | siphon gulp --format mp3` ingests as audio without sniffing.
7. `siphon gulp @clipboard /some/path` exits with code 1 and prints the correct error message.
8. `cat file.txt | siphon gulp /some/path` exits with code 1 and prints the correct error message.
9. `siphon gulp @clipboard` with empty clipboard exits with code 1.
10. `cat file.zip | siphon gulp` exits with code 1 (ZIP not DOCX).
11. Ingesting the same clipboard content twice results in a duplicate rejection (same hash), not two records.
12. On Linux, `siphon gulp @clipboard` exits with code 1 and the macOS-only message.

---

## Observability

- Log at `INFO` level when ephemeral input is resolved: source (`clipboard` or `stdin`), detected extension, byte count, computed hash.
- Log at `DEBUG` level when `ensure_temp_file()` creates and removes a temp file, including the temp path.
- Log at `WARNING` level if sniffing falls back to UTF-8 decode (ambiguous input).
- No new metrics or alerts are required for this feature. Pipeline-level metrics (ingest latency, error rate) cover it via existing instrumentation.
