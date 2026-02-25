from __future__ import annotations

# Parser tests: pure unit tests, no network
# Extractor tests: require network access to export.arxiv.org

import asyncio
import sys


def test_parser():
    from siphon_server.sources.arxiv.parser import ArxivParser

    parser = ArxivParser()

    # Bare ID
    assert parser.can_handle("2301.12345"), "bare 5-digit ID"
    assert parser.can_handle("2301.1234"), "bare 4-digit ID"
    assert parser.can_handle("https://arxiv.org/abs/2301.12345"), "abs URL"
    assert parser.can_handle("https://arxiv.org/pdf/2301.12345"), "pdf URL"
    assert not parser.can_handle("https://example.com"), "non-arxiv URL"
    assert not parser.can_handle("not-an-id"), "random string"

    info = parser.parse("2301.12345")
    assert info.uri == "arxiv:///2301.12345"
    assert info.hash is not None
    assert len(info.hash) == 16

    info2 = parser.parse("https://arxiv.org/abs/2301.12345")
    assert info2.uri == "arxiv:///2301.12345"

    info3 = parser.parse("https://arxiv.org/pdf/2301.12345v2")
    assert info3.uri == "arxiv:///2301.12345"

    print("Parser tests passed")


def test_extractor():
    # Requires network access to export.arxiv.org
    from siphon_server.sources.arxiv.parser import ArxivParser
    from siphon_server.sources.arxiv.extractor import ArxivExtractor

    parser = ArxivParser()
    extractor = ArxivExtractor()

    info = parser.parse("2301.07041")
    content = extractor.extract(info)
    assert content.text, "abstract should not be empty"
    assert "title" in content.metadata
    assert "authors" in content.metadata
    assert content.source_type.value == "Arxiv"
    print("Extractor tests passed")
    print(content.model_dump_json(indent=2))


async def test_enricher():
    # Requires network access + conduit model
    from siphon_server.sources.arxiv.parser import ArxivParser
    from siphon_server.sources.arxiv.extractor import ArxivExtractor
    from siphon_server.sources.arxiv.enricher import ArxivEnricher

    parser = ArxivParser()
    extractor = ArxivExtractor()
    enricher = ArxivEnricher()

    info = parser.parse("2301.07041")
    content = extractor.extract(info)
    enriched = await enricher.enrich(content)
    assert enriched.title
    assert enriched.description
    assert enriched.summary
    print("Enricher tests passed")
    print(enriched.model_dump_json(indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parser"
    if mode == "parser":
        test_parser()
    elif mode == "extractor":
        test_extractor()
    elif mode == "enricher":
        asyncio.run(test_enricher())
    else:
        print(f"Unknown mode: {mode}. Use: parser | extractor | enricher")
