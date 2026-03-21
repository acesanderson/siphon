import pytest
from pathlib import Path
from siphon_api.enums import SourceType
from siphon_api.models import SourceInfo, ContentData
from siphon_server.sources.doc.parser import DocParser
from siphon_server.sources.doc.extractor import DocExtractor
from siphon_server.sources.doc.enricher import DocEnricher


# === PARSER TESTS ===
@pytest.mark.parser
class TestDocParser:
    @pytest.fixture
    def parser(self):
        return DocParser()
    
    def test_can_handle_valid_source(self, parser):
        # TODO: Add valid source example
        pytest.skip("TODO: Implement can_handle test")
    
    def test_can_handle_invalid_source(self, parser):
        assert not parser.can_handle("https://example.com")
    
    def test_parse_extracts_identifier(self, parser):
        # TODO: Add parsing test
        pytest.skip("TODO: Implement parse test")
    
    def test_parse_creates_correct_uri(self, parser):
        # TODO: Verify URI format is "doc:///{identifier}"
        pytest.skip("TODO: Implement URI format test")


# === EXTRACTOR TESTS ===
@pytest.mark.extractor
class TestDocExtractor:
    @pytest.fixture
    def extractor(self):
        # TODO: Mock client dependency
        return DocExtractor()
    
    @pytest.fixture
    def sample_pdf(self):
        """Provide path to sample test PDF."""
        pdf_path = Path(__file__).parent.parent / "fixtures" / "sample_text.pdf"
        if not pdf_path.exists():
            pytest.skip("Test PDF fixture not found")
        return pdf_path

    @pytest.fixture
    def sample_source(self):
        # TODO: Create realistic sample SourceInfo
        return SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///sample_id",
            original_source="TODO: original URL",
            metadata={"identifier": "sample_id"}
        )

    def test_extract_returns_content_data(self, extractor, sample_pdf):
        """Test: extract() returns ContentData with non-empty text. AC-1.1"""
        source = SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///test",
            original_source=str(sample_pdf),
            hash="test_hash",
            metadata={}
        )

        content_data = extractor.extract(source)

        # AC-1.1: text field exists and is > 100 chars
        assert content_data.text is not None
        assert len(content_data.text) > 100, f"Expected > 100 chars, got {len(content_data.text)}"
        assert content_data.source_type == SourceType.DOC
        assert content_data.metadata is not None
    
    def test_extract_populates_text(self, extractor, sample_source):
        # TODO: Verify text field is populated
        pytest.skip("TODO: Verify text extraction")
    
    def test_extract_includes_metadata(self, extractor, sample_source):
        # TODO: Verify metadata is captured
        pytest.skip("TODO: Verify metadata extraction")


# === ENRICHER TESTS ===
@pytest.mark.enricher
class TestDocEnricher:
    @pytest.fixture
    def enricher(self):
        # TODO: Mock LLM client
        return DocEnricher(llm=None)
    
    @pytest.fixture
    def sample_content(self):
        # TODO: Create realistic sample ContentData
        return ContentData(
            source_type=SourceType.DOC,
            text="Sample content text here...",
            metadata={"title": "Sample Title"}
        )
    
    def test_enrich_generates_summary(self, enricher, sample_content):
        # TODO: Implement enrichment test
        pytest.skip("TODO: Implement enrich test")
    
    def test_enrich_extracts_topics(self, enricher, sample_content):
        # TODO: Verify topics extraction
        pytest.skip("TODO: Verify topics")
    
    def test_enrich_extracts_entities(self, enricher, sample_content):
        # TODO: Verify entities extraction
        pytest.skip("TODO: Verify entities")


# === INTEGRATION TEST ===
@pytest.mark.integration
class TestDocPipeline:
    def test_end_to_end_processing(self):
        """Full pipeline: parse → extract → enrich"""
        # TODO: Implement full pipeline test
        pytest.skip("TODO: Implement after all components work")
