import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from siphon_api.enums import SourceType
from siphon_api.models import SourceInfo, ContentData
from siphon_server.sources.doc.parser import DocParser
from siphon_server.sources.doc.extractor import DocExtractor
from siphon_server.sources.doc.enricher import DocEnricher
from docling_core.types.doc import (
    SectionHeaderItem,
    TextItem,
    ContentLayer,
    CodeItem,
    FormulaItem,
    ListItem,
)


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

    def test_heading_hierarchy_preserved(self, extractor):
        """Test: markdown output contains heading markers (##, ###, etc.). AC-1.3"""
        # Create mock DoclingDocument with headers
        mock_doc = Mock()

        # Create actual SectionHeaderItem and TextItem mocks
        header_item = Mock()
        header_item.__class__ = SectionHeaderItem
        header_item.text = "Section Title"
        header_item.level = 1

        text_item = Mock()
        text_item.__class__ = TextItem
        text_item.text = "This is the body text of the document."

        # Mock iterate_items to return header and text
        mock_doc.iterate_items.return_value = [
            (header_item, 1),
            (text_item, 2)
        ]

        # Test directly with the mock
        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.3: text should contain markdown heading markers (##)
        assert "##" in markdown, f"Expected markdown heading markers (##) in output, got: {markdown}"

    def test_text_output_preserves_length(self, extractor, sample_pdf):
        """Test: extracted text paragraphs preserve length > 100 chars. AC-1.4"""
        source = SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///test",
            original_source=str(sample_pdf),
            hash="test_hash",
            metadata={}
        )

        content_data = extractor.extract(source)
        markdown = content_data.text

        # AC-1.4: text output should be substantial
        assert len(markdown) > 100, f"Expected > 100 chars, got {len(markdown)}"

    def test_code_blocks_formatted_correctly(self, extractor):
        """Test: code blocks are formatted with markdown triple backticks. AC-1.1"""
        mock_doc = Mock()

        code_item = Mock()
        code_item.__class__ = CodeItem
        code_item.text = "def hello():\n    print('Hello, World!')"
        code_item.language = "python"

        mock_doc.iterate_items.return_value = [(code_item, 1)]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.1: code blocks should be wrapped in triple backticks with language
        assert "```python" in markdown, f"Expected ```python in output, got: {markdown}"
        assert "def hello()" in markdown, f"Expected code content in output, got: {markdown}"
        assert "```" in markdown, f"Expected closing backticks in output, got: {markdown}"

    def test_code_blocks_without_language(self, extractor):
        """Test: code blocks without language are still formatted. AC-1.1"""
        mock_doc = Mock()

        code_item = Mock()
        code_item.__class__ = CodeItem
        code_item.text = "some code here"
        # No language attribute

        mock_doc.iterate_items.return_value = [(code_item, 1)]

        markdown = extractor._docling_to_markdown(mock_doc)

        # Code should be wrapped in backticks even without language
        assert "```" in markdown, f"Expected backticks in output, got: {markdown}"
        assert "some code here" in markdown, f"Expected code content in output, got: {markdown}"

    def test_formulas_formatted_correctly(self, extractor):
        """Test: formulas are formatted with LaTeX delimiters. AC-1.1"""
        mock_doc = Mock()

        formula_item = Mock()
        formula_item.__class__ = FormulaItem
        formula_item.text = "E = mc^2"

        mock_doc.iterate_items.return_value = [(formula_item, 1)]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.1: formulas should be wrapped in $ delimiters
        assert "$E = mc^2$" in markdown, f"Expected $E = mc^2$ in output, got: {markdown}"

    def test_bullet_list_items_formatted_correctly(self, extractor):
        """Test: bullet list items are formatted with dashes. AC-1.1"""
        mock_doc = Mock()

        list_item = Mock()
        list_item.__class__ = ListItem
        list_item.text = "First item"
        list_item.is_bullet = True

        mock_doc.iterate_items.return_value = [(list_item, 1)]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.1: bullet list items should start with dash
        assert "- First item" in markdown, f"Expected '- First item' in output, got: {markdown}"

    def test_numbered_list_items_formatted_correctly(self, extractor):
        """Test: numbered list items are formatted with numbers. AC-1.1"""
        mock_doc = Mock()

        list_item = Mock()
        list_item.__class__ = ListItem
        list_item.text = "First step"
        list_item.is_bullet = False
        list_item.index = 1

        mock_doc.iterate_items.return_value = [(list_item, 1)]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.1: numbered list items should start with number and dot
        assert "1. First step" in markdown, f"Expected '1. First step' in output, got: {markdown}"

    def test_mixed_content_types(self, extractor):
        """Test: mixed content types (text, code, formula, lists) are all formatted. AC-1.1"""
        mock_doc = Mock()

        text_item = Mock()
        text_item.__class__ = TextItem
        text_item.text = "Introduction text"

        code_item = Mock()
        code_item.__class__ = CodeItem
        code_item.text = "print('hello')"
        code_item.language = "python"

        formula_item = Mock()
        formula_item.__class__ = FormulaItem
        formula_item.text = "x^2 + y^2"

        list_item = Mock()
        list_item.__class__ = ListItem
        list_item.text = "List item"
        list_item.is_bullet = True

        mock_doc.iterate_items.return_value = [
            (text_item, 1),
            (code_item, 2),
            (formula_item, 3),
            (list_item, 4),
        ]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.1: all content types should be present and formatted
        assert "Introduction text" in markdown, "Expected text content"
        assert "```python" in markdown, "Expected code block"
        assert "$x^2 + y^2$" in markdown, "Expected formula"
        assert "- List item" in markdown, "Expected list item"


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
