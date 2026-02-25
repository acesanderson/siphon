from __future__ import annotations

# Parser tests: pure unit tests, no network required for file existence checks
# Extractor tests: require a real image file or image URL + conduit vision model

import asyncio
import sys
from pathlib import Path


def test_parser_url():
    from siphon_server.sources.image.parser import ImageParser

    parser = ImageParser()

    assert parser.can_handle("https://example.com/photo.jpg"), "jpg URL"
    assert parser.can_handle("https://example.com/image.PNG"), "PNG URL case-insensitive"
    assert parser.can_handle("https://example.com/logo.svg"), "svg URL"
    assert not parser.can_handle("https://example.com/page.html"), "non-image URL"
    assert not parser.can_handle("https://example.com/"), "no extension URL"

    info = parser.parse("https://example.com/photo.jpg")
    assert info.uri.startswith("image:///jpg/")
    assert info.hash is not None
    assert len(info.hash) == 16
    print("Parser URL tests passed")


def test_parser_file(image_path: str):
    from siphon_server.sources.image.parser import ImageParser

    parser = ImageParser()
    p = Path(image_path)
    assert p.exists(), f"File not found: {image_path}"
    assert parser.can_handle(image_path), "should handle existing image file"
    info = parser.parse(image_path)
    assert info.uri.startswith("image:///")
    print(f"Parser file test passed for {image_path}")
    print(info.model_dump_json(indent=2))


def test_extractor(image_path: str):
    # Requires conduit vision model
    from siphon_server.sources.image.parser import ImageParser
    from siphon_server.sources.image.extractor import ImageExtractor

    parser = ImageParser()
    extractor = ImageExtractor()

    info = parser.parse(image_path)
    content = extractor.extract(info)
    assert content.text, "vision description should not be empty"
    print("Extractor test passed")
    print(content.model_dump_json(indent=2))


async def test_enricher(image_path: str):
    # Requires conduit vision model
    from siphon_server.sources.image.parser import ImageParser
    from siphon_server.sources.image.extractor import ImageExtractor
    from siphon_server.sources.image.enricher import ImageEnricher

    parser = ImageParser()
    extractor = ImageExtractor()
    enricher = ImageEnricher()

    info = parser.parse(image_path)
    content = extractor.extract(info)
    enriched = await enricher.enrich(content)
    assert enriched.title
    print("Enricher test passed")
    print(enriched.model_dump_json(indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parser_url"
    path = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode == "parser_url":
        test_parser_url()
    elif mode == "parser_file":
        test_parser_file(path)
    elif mode == "extractor":
        test_extractor(path)
    elif mode == "enricher":
        asyncio.run(test_enricher(path))
    else:
        print(f"Usage: test_image.py [parser_url|parser_file|extractor|enricher] [image_path]")
