from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo


class VideoExtractor(ExtractorStrategy):
    """Extract transcript from video by stripping audio with ffmpeg then transcribing."""

    source_type: SourceType = SourceType.VIDEO

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        from siphon_server.sources.audio.pipeline.audio_pipeline import retrieve_audio

        video_path = Path(source.original_source)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    str(tmp_path),
                ],
                check=True,
                capture_output=True,
            )
            text = retrieve_audio(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        metadata = {
            "file_name": video_path.name,
            "extension": video_path.suffix.lower(),
            "hash": source.hash,
        }
        return ContentData(
            source_type=self.source_type,
            text=text,
            metadata=metadata,
        )
