from __future__ import annotations

# Parser tests: require a real Obsidian vault on the filesystem
# Extractor tests: require the same vault with wikilinks

import asyncio
import sys
from pathlib import Path


def test_parser(note_path: str):
    from siphon_server.sources.obsidian.parser import ObsidianParser

    parser = ObsidianParser()

    p = Path(note_path)
    assert p.exists(), f"Note not found: {note_path}"
    result = parser.can_handle(note_path)
    print(f"can_handle({note_path}) = {result}")

    if result:
        info = parser.parse(note_path)
        assert info.uri.startswith("obsidian:///")
        # URI is the filename stem, not a hash
        assert info.uri == f"obsidian:///{p.stem}"
        print("Parser test passed")
        print(info.model_dump_json(indent=2))
    else:
        print("Note is not inside an Obsidian vault or is not a .md file")


def test_parser_negative():
    from siphon_server.sources.obsidian.parser import ObsidianParser

    parser = ObsidianParser()

    assert not parser.can_handle("/nonexistent/path/note.md"), "nonexistent file"
    assert not parser.can_handle("/tmp/test.txt"), "non-md file"
    print("Parser negative tests passed")


def test_extractor(note_path: str):
    from siphon_server.sources.obsidian.parser import ObsidianParser
    from siphon_server.sources.obsidian.extractor import ObsidianExtractor

    parser = ObsidianParser()
    extractor = ObsidianExtractor()

    info = parser.parse(note_path)
    content = extractor.extract(info)
    assert content.text, "note text should not be empty"
    assert "note_path" in content.metadata
    assert "vault_root" in content.metadata
    assert "wikilinks" in content.metadata
    assert isinstance(content.metadata["wikilinks"], list)
    # All wikilinks should be obsidian:/// URIs
    for link in content.metadata["wikilinks"]:
        assert link.startswith("obsidian:///"), f"bad wikilink URI: {link}"
    print("Extractor test passed")
    print(f"Wikilinks found: {len(content.metadata['wikilinks'])}")
    print(content.text[:500])


async def test_enricher(note_path: str):
    from siphon_server.sources.obsidian.parser import ObsidianParser
    from siphon_server.sources.obsidian.extractor import ObsidianExtractor
    from siphon_server.sources.obsidian.enricher import ObsidianEnricher

    parser = ObsidianParser()
    extractor = ObsidianExtractor()
    enricher = ObsidianEnricher()

    info = parser.parse(note_path)
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
    elif mode == "parser":
        test_parser(path)
    elif mode == "extractor":
        test_extractor(path)
    elif mode == "enricher":
        asyncio.run(test_enricher(path))
    else:
        print("Usage: test_obsidian.py [parser_negative|parser|extractor|enricher] [note_path]")
