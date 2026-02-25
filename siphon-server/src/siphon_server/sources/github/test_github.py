from __future__ import annotations

# Parser tests: pure unit tests, no network required
# Extractor tests: require network + optionally GITHUB_TOKEN env var for private repos

import asyncio
import sys


def test_parser():
    from siphon_server.sources.github.parser import GitHubParser

    parser = GitHubParser()

    assert parser.can_handle("https://github.com/owner/repo"), "basic repo URL"
    assert parser.can_handle("https://github.com/owner/repo.git"), "trailing .git"
    assert parser.can_handle("https://github.com/owner/repo/tree/main"), "/tree/ branch"
    assert parser.can_handle("https://github.com/owner/repo/blob/main/README.md"), "/blob/ file"
    assert not parser.can_handle("https://gitlab.com/owner/repo"), "GitLab excluded"
    assert not parser.can_handle("https://github.com/owner"), "no repo path"
    assert not parser.can_handle("https://example.com"), "non-github"

    info = parser.parse("https://github.com/owner/repo")
    assert info.uri == "github:///owner/repo"
    assert info.hash is not None
    assert len(info.hash) == 16

    info2 = parser.parse("https://github.com/owner/repo/tree/main/src")
    assert info2.uri == "github:///owner/repo"

    info3 = parser.parse("https://github.com/owner/repo.git")
    assert info3.uri == "github:///owner/repo"

    print("Parser tests passed")


def test_extractor(repo_url: str):
    # Requires network. Set GITHUB_TOKEN env var for private repos / higher rate limits.
    from siphon_server.sources.github.parser import GitHubParser
    from siphon_server.sources.github.extractor import GitHubExtractor

    parser = GitHubParser()
    extractor = GitHubExtractor()

    info = parser.parse(repo_url)
    content = extractor.extract(info)
    assert content.text, "xml blob should not be empty"
    assert "owner" in content.metadata
    print("Extractor test passed")
    print(f"File count: {content.metadata.get('file_count')}")
    print(content.text[:500])


async def test_enricher(repo_url: str):
    from siphon_server.sources.github.parser import GitHubParser
    from siphon_server.sources.github.extractor import GitHubExtractor
    from siphon_server.sources.github.enricher import GitHubEnricher

    parser = GitHubParser()
    extractor = GitHubExtractor()
    enricher = GitHubEnricher()

    info = parser.parse(repo_url)
    content = extractor.extract(info)
    enriched = await enricher.enrich(content)
    assert enriched.title
    print("Enricher test passed")
    print(enriched.model_dump_json(indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parser"
    url = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode == "parser":
        test_parser()
    elif mode == "extractor":
        test_extractor(url)
    elif mode == "enricher":
        asyncio.run(test_enricher(url))
    else:
        print("Usage: test_github.py [parser|extractor|enricher] [repo_url]")
