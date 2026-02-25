from __future__ import annotations

# Parser tests: pure unit tests, no network or auth required
# Extractor tests: require GMAIL_TOKEN_FILE and GMAIL_CLIENT_SECRET_FILE env vars
#   and a valid Gmail message ID to fetch

import asyncio
import sys


def test_parser():
    from siphon_server.sources.email.parser import EmailParser

    parser = EmailParser()

    # Gmail message URL
    url = "https://mail.google.com/mail/u/0/#inbox/18abc123def456ab"
    assert parser.can_handle(url), "Gmail URL"
    info = parser.parse(url)
    assert info.uri == "email:///gmail/18abc123def456ab"
    assert info.hash is not None

    # Bare message ID
    assert parser.can_handle("18abc123def456ab"), "bare 16-char hex ID"
    info2 = parser.parse("18abc123def456ab")
    assert info2.uri == "email:///gmail/18abc123def456ab"

    # Negative cases
    assert not parser.can_handle("https://example.com"), "non-gmail URL"
    assert not parser.can_handle("notanid"), "not a hex ID"
    assert not parser.can_handle("18ABC123DEF456AB"), "uppercase hex rejected"

    print("Parser tests passed")


def test_extractor(message_id: str):
    # Requires GMAIL_TOKEN_FILE and GMAIL_CLIENT_SECRET_FILE env vars
    from siphon_server.sources.email.parser import EmailParser
    from siphon_server.sources.email.extractor import EmailExtractor

    parser = EmailParser()
    extractor = EmailExtractor()

    info = parser.parse(message_id)
    content = extractor.extract(info)
    assert content.text, "email body should not be empty"
    assert "subject" in content.metadata
    print("Extractor test passed")
    print(content.model_dump_json(indent=2))


async def test_enricher(message_id: str):
    from siphon_server.sources.email.parser import EmailParser
    from siphon_server.sources.email.extractor import EmailExtractor
    from siphon_server.sources.email.enricher import EmailEnricher

    parser = EmailParser()
    extractor = EmailExtractor()
    enricher = EmailEnricher()

    info = parser.parse(message_id)
    content = extractor.extract(info)
    enriched = await enricher.enrich(content)
    assert enriched.title
    print("Enricher test passed")
    print(enriched.model_dump_json(indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parser"
    msg_id = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode == "parser":
        test_parser()
    elif mode == "extractor":
        test_extractor(msg_id)
    elif mode == "enricher":
        asyncio.run(test_enricher(msg_id))
    else:
        print("Usage: test_email.py [parser|extractor|enricher] [message_id]")
