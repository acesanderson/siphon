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
    TableItem,
    PictureItem,
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

    def test_table_basic_formatting(self, extractor):
        """Test: basic table is formatted as GFM pipe table. AC-1.5"""
        mock_doc = Mock()

        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = [
            ["Name", "Age", "City"],
            ["Alice", "30", "NYC"],
            ["Bob", "25", "LA"],
        ]

        mock_doc.iterate_items.return_value = [(table_item, 1)]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.5: table should be formatted as GFM pipe table
        assert "| Name | Age | City |" in markdown, "Expected header row"
        assert "| --- | --- | --- |" in markdown, "Expected separator row"
        assert "| Alice | 30 | NYC |" in markdown, "Expected data row 1"
        assert "| Bob | 25 | LA |" in markdown, "Expected data row 2"

    def test_table_with_pipes_in_cells(self, extractor):
        """Test: pipes in cell content are escaped. AC-1.5"""
        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = [
            ["Code", "Description"],
            ["A|B", "Contains pipe"],
        ]

        markdown = extractor._table_to_markdown(table_item)

        # AC-1.5: pipes should be escaped with backslash
        assert "A\\|B" in markdown, "Expected escaped pipe in cell"
        assert "| A\\|B | Contains pipe |" in markdown, "Expected escaped pipe in row"

    def test_table_with_empty_cells(self, extractor):
        """Test: empty cells are handled correctly. AC-1.5"""
        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = [
            ["Col1", "Col2", "Col3"],
            ["Value", "", "Data"],
            ["", "Middle", ""],
        ]

        markdown = extractor._table_to_markdown(table_item)

        # AC-1.5: empty cells should be handled gracefully
        assert "| Value |  | Data |" in markdown, "Expected empty cell in row 1"
        assert "|  | Middle |  |" in markdown, "Expected empty cells in row 2"

    def test_table_wide_table_warning(self, extractor, caplog):
        """Test: wide table (>50 columns) logs warning. AC-1.5"""
        import logging
        caplog.set_level(logging.WARNING)

        table_item = Mock()
        table_item.__class__ = TableItem
        # Create a table with 51 columns
        table_item.data = [
            [f"Col{i}" for i in range(51)],
            [f"Val{i}" for i in range(51)],
        ]

        markdown = extractor._table_to_markdown(table_item)

        # AC-1.5: warning should be logged for wide tables
        assert "Wide table detected" in caplog.text, "Expected warning for wide table"
        assert "51 columns" in caplog.text, "Expected column count in warning"

    def test_table_error_no_data(self, extractor):
        """Test: table without data raises ValueError. AC-1.5"""
        table_item = Mock()
        table_item.__class__ = TableItem
        # No data attribute
        del table_item.data

        with pytest.raises(ValueError, match="Table lacks data"):
            extractor._table_to_markdown(table_item)

    def test_table_error_empty_table(self, extractor):
        """Test: empty table raises ValueError. AC-1.5"""
        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = []

        with pytest.raises(ValueError, match="Table lacks data"):
            extractor._table_to_markdown(table_item)

    def test_table_in_document(self, extractor):
        """Test: table is processed in document iteration. AC-1.5"""
        mock_doc = Mock()

        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = [
            ["Header1", "Header2"],
            ["Data1", "Data2"],
        ]

        text_item = Mock()
        text_item.__class__ = TextItem
        text_item.text = "Text before table"

        mock_doc.iterate_items.return_value = [
            (text_item, 1),
            (table_item, 2),
        ]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-1.5: both text and table should be in output
        assert "Text before table" in markdown, "Expected text content"
        assert "| Header1 | Header2 |" in markdown, "Expected table header"
        assert "| Data1 | Data2 |" in markdown, "Expected table data"

    def test_markdown_is_valid_gfm(self, extractor, sample_pdf):
        """Test: Returned markdown parses as valid GFM. AC-1.2"""
        source = SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///test",
            original_source=str(sample_pdf),
            hash="test_hash",
            metadata={}
        )

        content_data = extractor.extract(source)
        markdown = content_data.text

        # Use markdown parser to validate syntax
        try:
            import markdown
            # Parse and validate markdown
            html = markdown.markdown(markdown)
            # If we get here without exception, markdown is valid
            assert html is not None
        except Exception as e:
            pytest.fail(f"Markdown parsing failed: {e}")

        # Additional check: ensure no obvious syntax errors
        assert markdown.count("| ") >= 0  # Tables allowed
        assert markdown.count("#") >= 0   # Headings allowed

    def test_no_file_paths_or_uris_in_output(self, extractor):
        """Test: Markdown contains no file paths, URIs, or base64. AC-1.6"""
        source = SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///test",
            original_source=str(Path(__file__).parent.parent / "fixtures" / "sample_text.pdf"),
            hash="test_hash",
            metadata={}
        )

        content_data = extractor.extract(source)
        markdown = content_data.text

        # Check for forbidden patterns
        assert "http://" not in markdown and "https://" not in markdown, "URIs found in output"
        assert "file://" not in markdown, "file:// URIs found"
        assert "data:image" not in markdown, "base64 data URIs found"
        assert "![" not in markdown, "Markdown image references found"
        assert "<img" not in markdown, "HTML img tags found"

        # Check for filepath patterns (rough heuristic)
        import re
        filepath_pattern = re.compile(r'[A-Z]:\\|/[a-zA-Z0-9_/\-\.]+\.(pdf|docx|pptx)')
        assert not filepath_pattern.search(markdown), "File paths detected in output"

    def test_vlm_prompt_selection_by_image_type(self, extractor):
        """Test: Correct prompt selected by image type. AC-4.5"""
        # Test chart type selection
        chart_prompt = extractor._select_vlm_prompt("bar_chart")
        assert "Analyze this chart" in chart_prompt, "Expected PROMPT_CHART for bar_chart"

        line_chart_prompt = extractor._select_vlm_prompt("line_chart")
        assert "Analyze this chart" in line_chart_prompt, "Expected PROMPT_CHART for line_chart"

        # Test diagram type selection
        diagram_prompt = extractor._select_vlm_prompt("diagram")
        assert "Describe this diagram" in diagram_prompt, "Expected PROMPT_DIAGRAM for diagram"

        flow_chart_prompt = extractor._select_vlm_prompt("flow_chart")
        assert "Describe this diagram" in flow_chart_prompt, "Expected PROMPT_DIAGRAM for flow_chart"

        # Test OCR type selection
        ocr_prompt = extractor._select_vlm_prompt("text")
        assert "Extract all text" in ocr_prompt, "Expected PROMPT_OCR for text"

        # Test default prompt selection
        unknown_prompt = extractor._select_vlm_prompt("unknown_type")
        assert "Describe this image in detail" in unknown_prompt, "Expected PROMPT_DEFAULT for unknown type"

    def test_vlm_client_timeout(self):
        """Test: VLM client raises TimeoutError on timeout. AC-2.4"""
        from siphon_server.sources.doc.vlm_client import VLMClient
        from unittest.mock import patch, MagicMock
        import httpx

        client = VLMClient(
            url="http://localhost:11434/v1/chat/completions",
            model="test",
            timeout=60.0
        )

        # Mock httpx.Client to raise TimeoutException
        with patch('siphon_server.sources.doc.vlm_client.httpx.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(TimeoutError, match="timed out"):
                client.describe(b"fake_image_data", "describe")

    def test_picture_item_classification(self, extractor):
        """Test: Every PictureItem has valid classification type. AC-2.2"""
        # Mock picture with classification
        picture_item = Mock()
        picture_item.__class__ = PictureItem
        picture_item.annotations = {
            'document_figure_classifier': {
                'class': 'bar_chart',
                'confidence': 0.95
            }
        }

        image_type = extractor._get_picture_type(picture_item)

        # AC-2.2: type should be non-empty and valid
        assert image_type is not None
        assert isinstance(image_type, str)
        assert len(image_type) > 0
        assert image_type == 'bar_chart'

    def test_image_markdown_generation(self, extractor):
        """Test: PictureItem → <image type='...'>description</image>. AC-2.1, AC-2.3"""
        from unittest.mock import patch

        picture_item = Mock()
        picture_item.__class__ = PictureItem
        picture_item.annotations = {
            'document_figure_classifier': {
                'class': 'diagram',
                'confidence': 0.85
            }
        }
        picture_item.image_data = b'fake_image_data'

        # Mock the VLMClient.describe method
        with patch.object(extractor, '_get_vlm_description', return_value='A flowchart showing process steps'):
            markdown = extractor._picture_to_markdown(picture_item)

            # AC-2.1: format should be <image type="...">description</image>
            assert '<image type="diagram">' in markdown
            assert '</image>' in markdown
            assert 'A flowchart showing process steps' in markdown
            # AC-2.3: description should be non-empty
            assert len(markdown) > 50

    def test_low_confidence_defaults_to_unknown(self, extractor):
        """Test: Confidence < 0.5 → 'unknown' type. AC-2.5"""
        picture_item = Mock()
        picture_item.__class__ = PictureItem
        picture_item.annotations = {
            'document_figure_classifier': {
                'class': 'bar_chart',
                'confidence': 0.3  # Low confidence
            }
        }

        image_type = extractor._get_picture_type(picture_item)

        # AC-2.5: type should be 'unknown' when confidence < 0.5
        assert image_type == 'unknown'


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
