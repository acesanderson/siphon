# Audio Pipeline Refactor: Multi-Backend Transcription + Optional Diarization

**Date:** 2026-04-08  
**Status:** Implemented

## Context

The siphon audio pipeline was designed to run on AlphaBlue (Ubuntu, CUDA) via HeadwaterServer.
Diarization was hardwired as always-on, and transcription used HuggingFace transformers with
`device=0` (CUDA-specific). Both assumptions break when running locally on Petrosian (M3 Pro,
Apple Silicon).

Goals:
- Enable local testing on Petrosian (fast feedback loops for development)
- Make diarization opt-in (off by default) — it requires a Docker microservice, long iteration
  cycles, and a dedicated setup session
- Add host detection so the correct Whisper backend is selected automatically
- Preserve the AlphaBlue production path unchanged

## Current Pipeline Interface

```
AudioExtractor.extract(source: SourceInfo) → ContentData
  └─ retrieve_audio(audio_path: Path) → str
      └─ guaranteed_wav_path(audio_path)        # context manager: any format → WAV
          ├─ diarize(wav_path)                  # HTTP to Docker microservice → DiarizationResponse
          ├─ transcribe(wav_path)               # HF Whisper (CUDA) → list[dict]
          ├─ combine(diarization, transcript)   # → list[dict{word, speaker, start_time, end_time}]
          └─ format(annotated_transcript)       # → str "[0.0s] SPEAKER_0: words..."
```

`format()` and `combine()` are fully coupled to diarization — they assume speaker data exists.

## Changes

### 1. `transcribe.py` — backend detection + normalized output

Platform check: `platform.system() == "Darwin" and platform.machine() == "arm64"` selects
mlx-whisper; otherwise falls back to HF transformers (CUDA path for AlphaBlue).

Output is normalized to `list[dict{text: str, start: float, end: float}]` regardless of backend.

- **macOS arm64:** `mlx_whisper.transcribe()` with `mlx-community/whisper-large-v3-mlx`
- **Linux/CUDA:** HF transformers pipeline with `openai/whisper-large-v3`, `device=0`, `float16`
  - Updated from `whisper-base` to `whisper-large-v3` (accuracy improvement)

### 2. `audio_pipeline.py` — diarize parameter

`retrieve_audio(audio_path: Path, diarize: bool = False) → str`

When `diarize=False` (default): skip `diarize()` + `combine()`, pass normalized transcript
chunks directly to `format_simple()`.

When `diarize=True`: full pipeline as before (requires Docker microservice running). Note:
`combine()` will need updating to accept the new normalized transcribe output before this
path is production-ready — deferred to diarization implementation session.

### 3. `format.py` — add `format_simple()`

New function for the no-diarization path:

```
format_simple(chunks: list[dict]) → str
Output: "[0.0s] text of segment\n..."
```

The existing `format()` function is preserved for the diarized path.

## Deferred Work

- Update `combine()` to accept the new normalized transcribe output format
- `--diarize` CLI flag on `siphon add audio`
- File upload / path resolution for the client→AlphaBlue boundary (audio files must exist
  on the server machine in production)

## Client/CLI Implications

No changes needed to SiphonClient or the CLI for this refactor. `AudioExtractor._extract()`
calls `retrieve_audio()` with no arguments, which now defaults to `diarize=False` — correct
for both local and AlphaBlue contexts.

Future: a `--diarize` flag would propagate as: CLI arg → `SourceInfo` extra field (or separate
config) → `AudioExtractor` → `retrieve_audio(diarize=True)`.

## Hardware Context

- **Petrosian** (dev): MacBook Pro M3 Pro, 18 GB unified memory — mlx-whisper path
- **AlphaBlue** (prod): Ubuntu, CUDA GPU — HF transformers path
- `mlx-whisper` installed into siphon-server venv via `uv pip install mlx-whisper`
- `mlx-whisper` is not in `pyproject.toml` as a hard dependency (macOS-only, platform-specific)

## Test Invocation

```
siphon-server/.venv/bin/python siphon-server/dev/transcribe_local.py ~/recordings/companyconnect0304.mp3
```
