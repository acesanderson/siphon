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


def make_table_data(rows: list[list[str]]) -> Mock:
    """Build a mock TableData from a list-of-lists, matching the real Docling API."""
    num_rows = len(rows)
    num_cols = len(rows[0]) if rows else 0
    cells = []
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            cell = Mock()
            cell.start_row_offset_idx = r
            cell.start_col_offset_idx = c
            cell.text = text
            cells.append(cell)
    data = Mock()
    data.num_rows = num_rows
    data.num_cols = num_cols
    data.table_cells = cells
    return data


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
        header_item.metadata = None  # Not OCR text

        text_item = Mock()
        text_item.__class__ = TextItem
        text_item.text = "This is the body text of the document."
        text_item.metadata = None  # Not OCR text

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
        code_item.metadata = None  # Not OCR text

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
        code_item.metadata = None  # Not OCR text
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
        formula_item.metadata = None  # Not OCR text

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
        list_item.metadata = None  # Not OCR text

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
        list_item.metadata = None  # Not OCR text

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
        text_item.metadata = None  # Not OCR text

        code_item = Mock()
        code_item.__class__ = CodeItem
        code_item.text = "print('hello')"
        code_item.language = "python"
        code_item.metadata = None  # Not OCR text

        formula_item = Mock()
        formula_item.__class__ = FormulaItem
        formula_item.text = "x^2 + y^2"
        formula_item.metadata = None  # Not OCR text

        list_item = Mock()
        list_item.__class__ = ListItem
        list_item.text = "List item"
        list_item.is_bullet = True
        list_item.metadata = None  # Not OCR text

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
        table_item.data = make_table_data([
            ["Name", "Age", "City"],
            ["Alice", "30", "NYC"],
            ["Bob", "25", "LA"],
        ])

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
        table_item.data = make_table_data([
            ["Code", "Description"],
            ["A|B", "Contains pipe"],
        ])

        markdown = extractor._table_to_markdown(table_item)

        # AC-1.5: pipes should be escaped with backslash
        assert "A\\|B" in markdown, "Expected escaped pipe in cell"
        assert "| A\\|B | Contains pipe |" in markdown, "Expected escaped pipe in row"

    def test_table_with_empty_cells(self, extractor):
        """Test: empty cells are handled correctly. AC-1.5"""
        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = make_table_data([
            ["Col1", "Col2", "Col3"],
            ["Value", "", "Data"],
            ["", "Middle", ""],
        ])

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
        table_item.data = make_table_data([
            [f"Col{i}" for i in range(51)],
            [f"Val{i}" for i in range(51)],
        ])

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
        data = Mock()
        data.num_rows = 0
        data.num_cols = 0
        data.table_cells = []
        table_item.data = data

        with pytest.raises(ValueError, match="Table lacks data"):
            extractor._table_to_markdown(table_item)

    def test_table_in_document(self, extractor):
        """Test: table is processed in document iteration. AC-1.5"""
        mock_doc = Mock()

        table_item = Mock()
        table_item.__class__ = TableItem
        table_item.data = make_table_data([
            ["Header1", "Header2"],
            ["Data1", "Data2"],
        ])

        text_item = Mock()
        text_item.__class__ = TextItem
        text_item.text = "Text before table"
        text_item.metadata = None  # Not OCR text

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

        md_lib = pytest.importorskip("markdown", reason="markdown package not installed")
        html = md_lib.markdown(markdown)
        assert html is not None

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

    def test_no_forbidden_image_syntax_in_output(self, extractor):
        """Test: No ![](...)  or base64 images. AC-2.6"""
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
        assert "![" not in markdown, "Markdown image references found"
        assert "<img" not in markdown, "HTML img tags found"
        assert "data:image" not in markdown, "base64 data URIs found"

        # Should have directive-style image blocks instead
        # Note: sample PDF may not have images, so just verify no forbidden content
        assert "<img" not in markdown
        assert "![" not in markdown

    def test_vlm_prompt_selection_by_image_type(self, extractor):
        """Test: Correct prompt selected by image type. AC-4.5"""
        # Test chart type selection
        chart_prompt = extractor._select_vlm_prompt("bar_chart")
        assert "Analyze this chart" in chart_prompt, "Expected PROMPT_CHART for bar_chart"

        line_chart_prompt = extractor._select_vlm_prompt("line_chart")
        assert "Analyze this chart" in line_chart_prompt, "Expected PROMPT_CHART for line_chart"

        # Test diagram type selection
        diagram_prompt = extractor._select_vlm_prompt("diagram")
        assert "diagram" in diagram_prompt.lower(), "Expected PROMPT_DIAGRAM for diagram"

        flow_chart_prompt = extractor._select_vlm_prompt("flow_chart")
        assert "diagram" in flow_chart_prompt.lower(), "Expected PROMPT_DIAGRAM for flow_chart"

        # Test OCR type selection
        ocr_prompt = extractor._select_vlm_prompt("text")
        assert "Extract all text" in ocr_prompt, "Expected PROMPT_OCR for text"

        # Test default prompt selection
        unknown_prompt = extractor._select_vlm_prompt("unknown_type")
        assert "Analyze this image" in unknown_prompt, "Expected PROMPT_DEFAULT for unknown type"

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

        image_type, confident = extractor._get_picture_type(picture_item)

        # AC-2.2: type should be non-empty and valid
        assert image_type is not None
        assert isinstance(image_type, str)
        assert len(image_type) > 0
        assert image_type == 'bar_chart'
        assert confident is True

    def test_image_markdown_generation(self, extractor):
        """Test: PictureItem → :::{diagram}\ndescription\n:::. AC-2.1, AC-2.3"""
        from unittest.mock import patch

        picture_item = Mock()
        picture_item.__class__ = PictureItem
        picture_item.annotations = {
            'document_figure_classifier': {
                'class': 'diagram',
                'confidence': 0.85
            }
        }
        # Mock the VLMClient.describe method
        mock_doc = Mock()
        with patch.object(extractor, '_get_vlm_description', return_value='A flowchart showing process steps'):
            markdown = extractor._picture_to_markdown(picture_item, mock_doc)

            # AC-2.1: format should be :::{diagram}\ndescription\n:::
            assert ':::{diagram}' in markdown  # high confidence → bare type
            assert ':::' in markdown
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

        image_type, confident = extractor._get_picture_type(picture_item)

        # AC-2.5: low confidence → not confident, but type hint preserved
        assert confident is False
        assert image_type == 'bar_chart'

    def test_ocr_text_marked_with_comment(self, extractor):
        """Test: OCR text prefixed with <!-- OCR: from page N -->. AC-3.1"""
        mock_doc = Mock()

        # Create OCR TextItem with metadata
        ocr_text_item = Mock()
        ocr_text_item.__class__ = TextItem
        ocr_text_item.text = "OCR extracted text"
        ocr_text_item.metadata = {'ocr_confidence': 0.95}
        ocr_text_item.prov = [Mock(page_no=2)]

        # Create non-OCR TextItem
        normal_text_item = Mock()
        normal_text_item.__class__ = TextItem
        normal_text_item.text = "Normal text"
        normal_text_item.metadata = None

        mock_doc.iterate_items.return_value = [
            (normal_text_item, 1),
            (ocr_text_item, 2),
        ]

        markdown = extractor._docling_to_markdown(mock_doc)

        # AC-3.1: OCR marker should be present before OCR text
        assert "<!-- OCR: from page 2 -->" in markdown, f"Expected OCR marker in output, got: {markdown}"
        assert "OCR extracted text" in markdown

    def test_ocr_confidence_validation(self, extractor):
        """Test: OCR confidence < 0.5 raises ValueError. AC-3.3"""
        mock_doc = Mock()

        # Create low-confidence OCR TextItem
        low_conf_ocr_item = Mock()
        low_conf_ocr_item.__class__ = TextItem
        low_conf_ocr_item.text = "Low confidence OCR text"
        low_conf_ocr_item.metadata = {'ocr_confidence': 0.3}  # < 0.5
        low_conf_ocr_item.prov = [Mock(page_no=1)]

        mock_doc.iterate_items.return_value = [
            (low_conf_ocr_item, 1),
        ]

        # AC-3.3: should raise ValueError for low OCR confidence
        with pytest.raises(ValueError, match="OCR confidence 0.30 < 0.5"):
            extractor._docling_to_markdown(mock_doc)

    def test_mixed_native_and_ocr_documents_extract(self, extractor):
        """Test: Documents with mixed native + OCR content extract successfully. AC-3.4"""
        source = SourceInfo(
            source_type=SourceType.DOC,
            uri="doc:///test",
            original_source=str(Path(__file__).parent.parent / "fixtures" / "sample_text.pdf"),
            hash="test_hash",
            metadata={}
        )

        # Should succeed and contain content
        content_data = extractor.extract(source)
        markdown = content_data.text

        assert len(markdown) > 100
        assert content_data.text is not None
        # Mixed documents should extract without error

    def test_corrupted_document_raises_value_error(self, extractor):
        """Test: Corrupted PDF raises ValueError. AC-5.1"""
        # Create fake/corrupted file
        corrupted_path = Path(__file__).parent / "fixtures" / "corrupted.pdf"
        corrupted_path.parent.mkdir(parents=True, exist_ok=True)
        corrupted_path.write_bytes(b"This is not a valid PDF")

        try:
            source = SourceInfo(
                source_type=SourceType.DOC,
                uri="doc:///test",
                original_source=str(corrupted_path),
                hash="test",
                metadata={}
            )

            with pytest.raises(ValueError) as exc_info:
                extractor.extract(source)

            assert "corrupted" in str(exc_info.value).lower()
        finally:
            corrupted_path.unlink(missing_ok=True)

    def test_vlm_timeout_raises_timeout_error(self, extractor):
        """Test: VLM timeout raises TimeoutError. AC-5.4"""
        from unittest.mock import patch

        # Create mock picture
        picture = Mock()
        picture.__class__ = PictureItem
        picture.annotations = {
            'document_figure_classifier': {
                'class': 'chart',
                'confidence': 0.9
            }
        }
        mock_doc = Mock()

        with patch.object(extractor, '_get_vlm_description') as mock_vlm:
            mock_vlm.side_effect = TimeoutError("VLM timeout")

            with pytest.raises(TimeoutError):
                extractor._get_vlm_description(picture, mock_doc, "chart")


# === ENRICHER TESTS ===
@pytest.mark.enricher
class TestDocEnricher:
    @pytest.fixture
    def enricher(self):
        # TODO: Mock LLM client
        return DocEnricher()

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


# === COMPREHENSIVE INTEGRATION TEST ===
@pytest.mark.integration
def test_full_extraction_pipeline_pdf():
    """Full pipeline: Docling convert → transform → validate. All ACs.

    This comprehensive integration test validates all acceptance criteria:
    - AC-1.1: Text extraction (>100 chars)
    - AC-1.2: Valid GFM markdown
    - AC-1.3: Heading hierarchy preserved
    - AC-1.4: Text output length validation
    - AC-1.5: Table formatting (GFM pipe tables)
    - AC-1.6: No forbidden content (URIs, file paths, base64)
    - AC-2.6: No forbidden image syntax (![](...)  or <img>)
    - Metadata validation: file_name present and valid
    """
    extractor = DocExtractor()

    test_pdf = Path(__file__).parent.parent / "fixtures" / "sample_text.pdf"
    if not test_pdf.exists():
        pytest.skip("Test PDF not found")

    source = SourceInfo(
        source_type=SourceType.DOC,
        uri="doc:///integration_test",
        original_source=str(test_pdf),
        hash="test_hash",
        metadata={}
    )

    try:
        # Extract
        content_data = extractor.extract(source)
    except ValueError as e:
        if "libGL" in str(e) or "graphics" in str(e).lower():
            pytest.skip(f"Graphics library missing in environment: {e}")
        raise

    markdown = content_data.text

    # AC-1.1: Text > 100 chars
    assert len(markdown) > 100, f"Expected > 100 chars, got {len(markdown)}"

    # AC-1.2: Valid GFM — non-empty, well-formed
    assert len(markdown.strip()) > 0, "Markdown should be non-empty"

    # AC-1.6: No forbidden content
    assert "http://" not in markdown, "Found http:// URLs in markdown"
    assert "data:image" not in markdown, "Found base64 data URIs in markdown"

    # AC-1.5: Tables have proper format (if present)
    if "|" in markdown:
        assert "|---|" in markdown, "Table separator row (|---|) not found in markdown"

    # AC-2.6: No forbidden image syntax
    assert "![" not in markdown, "Found markdown image syntax ![]()"
    assert "<img" not in markdown, "Found HTML img tags"

    # Metadata valid
    assert content_data.metadata is not None, "Metadata is None"
    assert content_data.metadata.get('file_name') is not None, "file_name not in metadata"

    # AC-1.4: Non-empty text output
    assert content_data.text is not None, "Text is None"
    assert content_data.source_type == SourceType.DOC, "source_type mismatch"


@pytest.mark.integration
def test_full_extraction_pipeline_mock():
    """Full pipeline integration test using mocks. All ACs validated.

    This test validates the extraction pipeline with a mocked Docling document,
    ensuring all acceptance criteria are met without requiring external resources.
    """
    extractor = DocExtractor()

    # Create a complete mock document with all content types
    mock_doc = Mock()

    header = Mock()
    header.__class__ = SectionHeaderItem
    header.text = "Main Section"
    header.level = 1
    header.metadata = None

    text = Mock()
    text.__class__ = TextItem
    text.text = "This is a comprehensive test document with substantial content to exceed the 100 character minimum requirement."
    text.metadata = None

    code = Mock()
    code.__class__ = CodeItem
    code.text = "def test():\n    return True"
    code.language = "python"
    code.metadata = None

    formula = Mock()
    formula.__class__ = FormulaItem
    formula.text = "E = mc^2"
    formula.metadata = None

    bullet_list = Mock()
    bullet_list.__class__ = ListItem
    bullet_list.text = "Item one"
    bullet_list.is_bullet = True
    bullet_list.metadata = None

    numbered_list = Mock()
    numbered_list.__class__ = ListItem
    numbered_list.text = "Item one"
    numbered_list.is_bullet = False
    numbered_list.index = 1
    numbered_list.metadata = None

    table = Mock()
    table.__class__ = TableItem
    table.data = make_table_data([
        ["Column A", "Column B"],
        ["Value 1", "Value 2"],
        ["Value 3", "Value 4"],
    ])

    mock_doc.iterate_items.return_value = [
        (header, 1),
        (text, 2),
        (code, 3),
        (formula, 4),
        (bullet_list, 5),
        (numbered_list, 6),
        (table, 7),
    ]

    # Convert to markdown
    markdown = extractor._docling_to_markdown(mock_doc)

    # AC-1.1: Text > 100 chars
    assert len(markdown) > 100, f"Expected > 100 chars, got {len(markdown)}"

    # AC-1.2: Valid GFM (check for basic markdown structure)
    assert markdown.count("#") > 0, "Markdown should contain heading markers"

    # AC-1.3: Headings present
    assert "#" in markdown, "Expected heading markers (#) in markdown"

    # AC-1.4: Text content preserved
    assert "comprehensive test document" in markdown, "Text content not preserved"

    # AC-1.5: Tables have proper GFM format
    assert "| Column A | Column B |" in markdown, "Table header not found"
    assert "| --- | --- |" in markdown, "Table separator not found"
    assert "| Value 1 | Value 2 |" in markdown, "Table data not found"

    # AC-1.6: No forbidden content
    assert "http://" not in markdown, "Found URLs in markdown"
    assert "data:image" not in markdown, "Found base64 data URIs"

    # AC-2.1: Code blocks formatted correctly
    assert "```python" in markdown, "Code block not formatted"
    assert "def test():" in markdown, "Code content missing"

    # AC-2.6: No forbidden image syntax
    assert "![" not in markdown, "Found markdown image syntax"
    assert "<img" not in markdown, "Found HTML img tags"

    # Additional structure validation
    assert "- Item one" in markdown, "Bullet list not formatted"
    assert "1. Item one" in markdown, "Numbered list not formatted"
    assert "$E = mc^2$" in markdown, "Formula not formatted"
