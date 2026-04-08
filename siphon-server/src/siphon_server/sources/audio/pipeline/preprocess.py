from __future__ import annotations

import shutil
import subprocess
import tempfile
import logging
from contextlib import contextmanager
from pathlib import Path

from siphon_api.file_types import EXTENSIONS

logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"


@contextmanager
def guaranteed_wav_path(input_path: Path):
    """
    Context manager that guarantees a WAV file path for downstream processing.

    Yields the original path unchanged for WAV inputs. For all other formats,
    converts to a temporary WAV via ffmpeg and deletes it on exit.
    """
    suffix = input_path.suffix.lower()
    if suffix not in EXTENSIONS["Audio"]:
        raise ValueError(f"Unsupported audio format: {suffix}")

    if suffix == ".wav":
        logger.debug(f"[PREPROCESS] Input is already a WAV: {input_path}")
        yield input_path
        return

    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        logger.debug(f"[PREPROCESS] Converting {input_path} to temp WAV: {tmp.name}")
        subprocess.run(
            [_FFMPEG, "-i", str(input_path), "-y", tmp.name],
            check=True,
            capture_output=True,
        )
        yield Path(tmp.name)
    finally:
        if tmp:
            Path(tmp.name).unlink(missing_ok=True)
            logger.debug(f"[PREPROCESS] Temp WAV deleted: {tmp.name}")
