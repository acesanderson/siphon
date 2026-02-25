from __future__ import annotations

# Parser tests: pure unit tests, no network required (file existence checks skipped)
# Extractor tests: require a real video file + ffmpeg installed

import asyncio
import sys
from pathlib import Path


def test_parser_negative():
    from siphon_server.sources.video.parser import VideoParser

    parser = VideoParser()

    assert not parser.can_handle("https://youtube.com/watch?v=abc"), "YouTube URL excluded"
    assert not parser.can_handle("https://youtu.be/abc"), "youtu.be excluded"
    assert not parser.can_handle("not_a_video.txt"), "text file"
    assert not parser.can_handle("/nonexistent/path/video.mp4"), "nonexistent file"
    print("Parser negative tests passed")


def test_parser_file(video_path: str):
    from siphon_server.sources.video.parser import VideoParser

    parser = VideoParser()
    p = Path(video_path)
    assert p.exists(), f"File not found: {video_path}"
    assert parser.can_handle(video_path), "should handle existing video file"
    info = parser.parse(video_path)
    assert info.uri.startswith("video:///")
    assert info.hash is not None
    print(f"Parser file test passed for {video_path}")
    print(info.model_dump_json(indent=2))


def test_extractor(video_path: str):
    # Requires ffmpeg installed and a real video file
    from siphon_server.sources.video.parser import VideoParser
    from siphon_server.sources.video.extractor import VideoExtractor

    parser = VideoParser()
    extractor = VideoExtractor()

    info = parser.parse(video_path)
    content = extractor.extract(info)
    assert content.text, "transcript should not be empty"
    print("Extractor test passed")
    print(content.model_dump_json(indent=2))


async def test_enricher(video_path: str):
    from siphon_server.sources.video.parser import VideoParser
    from siphon_server.sources.video.extractor import VideoExtractor
    from siphon_server.sources.video.enricher import VideoEnricher

    parser = VideoParser()
    extractor = VideoExtractor()
    enricher = VideoEnricher()

    info = parser.parse(video_path)
    content = extractor.extract(info)
    enriched = await enricher.enrich(content)
    assert enriched.title
    print("Enricher test passed")
    print(enriched.model_dump_json(indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parser_negative"
    path = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode == "parser_negative":
        test_parser_negative()
    elif mode == "parser_file":
        test_parser_file(path)
    elif mode == "extractor":
        test_extractor(path)
    elif mode == "enricher":
        asyncio.run(test_enricher(path))
    else:
        print("Usage: test_video.py [parser_negative|parser_file|extractor|enricher] [video_path]")
