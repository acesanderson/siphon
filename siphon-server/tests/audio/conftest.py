from __future__ import annotations
import pytest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent.parent.parent / "examples"


@pytest.fixture
def aieng_mp3() -> Path:
    path = EXAMPLES_DIR / "aieng.mp3"
    assert path.exists(), f"Example MP3 not found: {path}"
    return path


@pytest.fixture
def bersin_mp3() -> Path:
    path = EXAMPLES_DIR / "bersin_on_coursera.mp3"
    assert path.exists(), f"Example MP3 not found: {path}"
    return path
