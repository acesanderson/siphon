from __future__ import annotations
import asyncio
import pytest
from pathlib import Path

from siphon_api.enums import SourceType
from siphon_api.models import ContentData, EnrichedData, SourceInfo
from siphon_server.sources.audio.enricher import AudioEnricher
from siphon_server.sources.audio.extractor import AudioExtractor
from siphon_server.sources.audio.parser import AudioParser


# === PARSER TESTS ===
@pytest.mark.parser
class TestAudioParser:
    @pytest.fixture
    def parser(self) -> AudioParser:
        return AudioParser()

    def test_can_handle_mp3(self, parser: AudioParser, aieng_mp3: Path) -> None:
        assert parser.can_handle(str(aieng_mp3))

    def test_cannot_handle_url(self, parser: AudioParser) -> None:
        assert not parser.can_handle("https://example.com/audio.mp3")

    def test_cannot_handle_nonexistent_path(self, parser: AudioParser) -> None:
        assert not parser.can_handle("/tmp/this_file_does_not_exist.mp3")

    def test_cannot_handle_non_audio_extension(
        self, parser: AudioParser, tmp_path: Path
    ) -> None:
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        assert not parser.can_handle(str(txt_file))

    def test_parse_returns_source_info(
        self, parser: AudioParser, aieng_mp3: Path
    ) -> None:
        info = parser.parse(str(aieng_mp3))
        assert isinstance(info, SourceInfo)
        assert info.source_type == SourceType.AUDIO

    def test_parse_uri_format(self, parser: AudioParser, aieng_mp3: Path) -> None:
        info = parser.parse(str(aieng_mp3))
        assert info.uri.startswith("audio:///mp3/")

    def test_parse_preserves_original_source(
        self, parser: AudioParser, aieng_mp3: Path
    ) -> None:
        info = parser.parse(str(aieng_mp3))
        assert info.original_source == str(aieng_mp3)

    def test_parse_hash_length(self, parser: AudioParser, aieng_mp3: Path) -> None:
        info = parser.parse(str(aieng_mp3))
        assert info.hash is not None
        assert len(info.hash) == 16

    def test_parse_is_deterministic(
        self, parser: AudioParser, aieng_mp3: Path
    ) -> None:
        info1 = parser.parse(str(aieng_mp3))
        info2 = parser.parse(str(aieng_mp3))
        assert info1.uri == info2.uri
        assert info1.hash == info2.hash

    def test_different_files_different_uri(
        self, parser: AudioParser, aieng_mp3: Path, bersin_mp3: Path
    ) -> None:
        info1 = parser.parse(str(aieng_mp3))
        info2 = parser.parse(str(bersin_mp3))
        assert info1.hash != info2.hash
        assert info1.uri != info2.uri


# === EXTRACTOR TESTS ===
# Requires: diarization service running at localhost:8000, GPU for Whisper
@pytest.mark.integration
class TestAudioExtractor:
    @pytest.fixture
    def extractor(self) -> AudioExtractor:
        return AudioExtractor()

    @pytest.fixture
    def aieng_source_info(self, aieng_mp3: Path) -> SourceInfo:
        return AudioParser().parse(str(aieng_mp3))

    def test_extract_returns_content_data(
        self, extractor: AudioExtractor, aieng_source_info: SourceInfo
    ) -> None:
        content = extractor.extract(aieng_source_info)
        assert isinstance(content, ContentData)
        assert content.source_type == SourceType.AUDIO

    def test_extract_text_is_non_empty(
        self, extractor: AudioExtractor, aieng_source_info: SourceInfo
    ) -> None:
        content = extractor.extract(aieng_source_info)
        assert isinstance(content.text, str)
        assert len(content.text) > 0

    def test_extract_metadata_fields(
        self, extractor: AudioExtractor, aieng_source_info: SourceInfo
    ) -> None:
        content = extractor.extract(aieng_source_info)
        for field in ("file_name", "hash", "extension", "mime_type", "file_size"):
            assert field in content.metadata, f"Missing metadata field: {field}"
        assert content.metadata["extension"] == ".mp3"
        assert content.metadata["mime_type"] == "audio/mpeg"

    def test_extract_wrong_source_type_raises(
        self, extractor: AudioExtractor
    ) -> None:
        bad_source = SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///pdf/abc123",
            original_source="/tmp/fake.pdf",
        )
        with pytest.raises(ValueError):
            extractor.extract(bad_source)


# === FULL GULP TESTS ===
# Requires: diarization service, GPU for Whisper, LLM access via conduit
@pytest.mark.e2e
class TestAudioGulp:
    """Full parse → extract → enrich pipeline using real mp3 examples."""

    def test_gulp_aieng(self, aieng_mp3: Path) -> None:
        parser = AudioParser()
        extractor = AudioExtractor()
        enricher = AudioEnricher()

        source_info = parser.parse(str(aieng_mp3))
        content_data = extractor.extract(source_info)
        enriched = asyncio.run(enricher.enrich(content_data))

        assert isinstance(enriched, EnrichedData)
        assert enriched.source_type == SourceType.AUDIO
        assert enriched.title
        assert enriched.description
        assert enriched.summary

    def test_gulp_bersin(self, bersin_mp3: Path) -> None:
        parser = AudioParser()
        extractor = AudioExtractor()
        enricher = AudioEnricher()

        source_info = parser.parse(str(bersin_mp3))
        content_data = extractor.extract(source_info)
        enriched = asyncio.run(enricher.enrich(content_data))

        assert isinstance(enriched, EnrichedData)
        assert enriched.source_type == SourceType.AUDIO
        assert enriched.title
        assert enriched.description
        assert enriched.summary
