from __future__ import annotations

import threading
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import SourceInfo, ContentData
from siphon_api.enums import SourceType
from siphon_api.metadata import FileMetadata
from siphon_api.file_types import MIME_TYPES
from datetime import datetime, timezone
from pathlib import Path
from typing import override
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import (
    DoclingDocument,
    SectionHeaderItem,
    TextItem,
    ContentLayer,
    CodeItem,
    FormulaItem,
    ListItem,
    TableItem,
    PictureItem,
)
from siphon_server.sources.doc.vlm_client import VLMClient
from typing import Optional


class DocExtractor(ExtractorStrategy):
    """
    Extract content from Doc: i.e. .doc, .docx files.
    """

    source_type: SourceType = SourceType.DOC

    def __init__(self) -> None:
        from siphon_server.config import settings
        self._semaphore = threading.Semaphore(settings.docling_vlm_concurrency)

    # VLM prompt templates
    PROMPT_OCR = """## INSTRUCTIONS
Extract all text, tables, headings, and structure from the document image.
Output clean, valid Markdown. Preserve hierarchy. Do not hallucinate content.

## INPUTS
An image (attached to message).
Focus on: headings (#/##/###), paragraphs, lists, tables (pipe syntax), bold/italic.

## CONSTRAINTS
- Only include content visible in the image
- Mark uncertain text as [UNCERTAIN], unreadable as [ILLEGIBLE]
- No summaries, additions, explanations, disclaimers, or meta-commentary
- No phrases like "Please note", "It should be noted", "I cannot", "Overall"

## OUTPUT FORMAT
Valid Markdown only. Title as H1, sections as H2/H3. No JSON wrappers or preamble."""

    PROMPT_CHART = """## INSTRUCTIONS
Analyze this chart. Answer these questions concisely:
1. What is being measured or compared?
2. What are the approximate values or ranges shown?
3. What is the key trend, pattern, or finding?
4. What conclusion does the chart support?

## CONSTRAINTS
- Focus on meaning and data, not aesthetics (skip colors and layout unless they encode information)
- Use approximate values when exact figures are not labeled
- No summary or concluding paragraphs
- No disclaimers, no "Please note", "Overall", "In summary", "It should be noted"
- No meta-commentary about what you cannot determine"""

    PROMPT_DIAGRAM = """## INSTRUCTIONS
Explain what this diagram shows. Answer these questions concisely:
1. What system, process, or concept does this depict?
2. What are the key components or steps?
3. How do they relate or connect?
4. What is the diagram communicating?

## CONSTRAINTS
- Focus on meaning and relationships, not aesthetics
- No summary or concluding paragraphs
- No disclaimers, no "Please note", "Overall", "In summary", "It should be noted"
- No meta-commentary about what you cannot determine"""

    PROMPT_DEFAULT = """## INSTRUCTIONS
Analyze this image. Answer these questions concisely:
1. What does this image show?
2. What is the key information, finding, or message it conveys?
3. If it contains data or a visualization: what are the values, trends, or patterns?

## CONSTRAINTS
- Focus on content and meaning, not aesthetics (skip colors and layout unless they encode information)
- No closing or contextualizing sentence at the end
- No summary paragraphs
- No disclaimers, no "Please note", "Overall", "In summary", "It should be noted"
- No meta-commentary about the source or context of the image"""

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        text = self._extract(source)
        metadata = self._generate_metadata(source)
        return ContentData(source_type=self.source_type, text=text, metadata=metadata)

    def _extract(self, source: SourceInfo) -> str:
        """Extract markdown text from document."""
        path = Path(source.original_source)

        # Docling convert — semaphore caps concurrent GPU calls
        with self._semaphore:
            doc = self._docling_convert(path)

        # Transform to markdown using core transformer
        markdown = self._docling_to_markdown(doc)

        return markdown

    def _is_ocr_text(self, item: TextItem) -> bool:
        """Check if text was recovered via OCR. AC-3.2: only when OCR source"""
        if not hasattr(item, 'metadata') or item.metadata is None:
            return False
        ocr_conf = item.metadata.get('ocr_confidence')
        return ocr_conf is not None

    def _get_page_no(self, item: TextItem) -> Optional[int]:
        """Extract page number from provenance."""
        if hasattr(item, 'prov') and item.prov:
            return item.prov[0].page_no
        return None

    def _validate_ocr_confidence(self, doc: DoclingDocument) -> None:
        """Validate all OCR text has confidence >= 0.5. AC-3.3"""
        for item, _ in doc.iterate_items(included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE}):
            # Check for TextItem but exclude subclasses like SectionHeaderItem, CodeItem, etc
            if type(item) == TextItem or (isinstance(item, TextItem) and
                                          not isinstance(item, (SectionHeaderItem, CodeItem,
                                                              FormulaItem, ListItem))):
                if self._is_ocr_text(item):
                    ocr_conf = item.metadata.get('ocr_confidence', 1.0)
                    if ocr_conf < 0.5:
                        page_no = self._get_page_no(item)
                        raise ValueError(
                            f"OCR confidence {ocr_conf:.2f} < 0.5 on page {page_no}; "
                            f"text unreadable"
                        )

    def _docling_to_markdown(self, doc: DoclingDocument) -> str:
        """Validate OCR first, then transform."""
        if doc is None:
            raise RuntimeError("DoclingDocument is None or invalid")

        # Validate OCR before processing (AC-3.3)
        self._validate_ocr_confidence(doc)

        parts = []
        prev_ocr = False  # Track OCR state for grouping

        # Iterate document content
        for item, depth in doc.iterate_items(included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE}):
            if isinstance(item, SectionHeaderItem):
                # Create heading: level determines # count
                heading_level = max(2, getattr(item, 'level', 2) + 1)
                heading_marker = "#" * heading_level
                parts.append(f"{heading_marker} {item.text}\n\n")
                prev_ocr = False

            elif isinstance(item, CodeItem):
                # Code block with language identifier
                # Note: Check CodeItem before TextItem since CodeItem is a subclass of TextItem
                lang = getattr(item, 'language', '')
                parts.append(f"```{lang}\n{item.text}\n```\n\n")
                prev_ocr = False

            elif isinstance(item, FormulaItem):
                # Mathematical formula in LaTeX format
                # Note: Check FormulaItem before TextItem since FormulaItem is a subclass of TextItem
                parts.append(f"${item.text}$\n\n")
                prev_ocr = False

            elif isinstance(item, ListItem):
                # List item (bullet or numbered)
                # Note: Check ListItem before TextItem since ListItem is a subclass of TextItem
                is_bullet = getattr(item, 'is_bullet', True)
                bullet_marker = "-" if is_bullet else f"{getattr(item, 'index', 1)}."
                parts.append(f"{bullet_marker} {item.text}\n")
                prev_ocr = False

            elif isinstance(item, TableItem):
                # GFM pipe table
                parts.append(self._table_to_markdown(item))
                prev_ocr = False

            elif isinstance(item, PictureItem):
                # Picture with VLM description
                parts.append(self._picture_to_markdown(item, doc))
                prev_ocr = False

            elif isinstance(item, TextItem):
                # Simple text paragraph
                is_ocr = self._is_ocr_text(item)

                # Emit OCR marker when transitioning to OCR text (AC-3.1)
                if is_ocr and not prev_ocr:
                    page_no = self._get_page_no(item)
                    parts.append(f"<!-- OCR: from page {page_no} -->\n")

                parts.append(f"{item.text}\n\n")
                prev_ocr = is_ocr

        return "".join(parts)

    def _table_to_markdown(self, table: TableItem) -> str:
        """Convert TableItem to GFM pipe table."""
        import logging

        data = getattr(table, 'data', None)
        if not data or not hasattr(data, 'num_rows') or data.num_rows == 0 or data.num_cols == 0:
            raise ValueError("Table lacks data")

        num_rows = data.num_rows
        num_cols = data.num_cols

        # Build grid from flat cell list
        grid: list[list[str]] = [[""] * num_cols for _ in range(num_rows)]
        for cell in data.table_cells:
            r = cell.start_row_offset_idx
            c = cell.start_col_offset_idx
            if r < num_rows and c < num_cols:
                grid[r][c] = str(cell.text).replace("|", "\\|")

        if num_cols > 50:
            logging.warning(f"Wide table detected: {num_cols} columns.")

        markdown_lines = []
        for i, row in enumerate(grid):
            markdown_lines.append("| " + " | ".join(row) + " |")
            if i == 0:
                markdown_lines.append("| " + " | ".join(["---"] * num_cols) + " |")

        return "\n".join(markdown_lines) + "\n\n"

    def _get_picture_type(self, picture: PictureItem) -> tuple[str, bool]:
        """Extract classification type from picture.

        Returns (type_label, confident) where:
        - confident=True, type_label='bar_chart'    → high confidence classification
        - confident=False, type_label='bar_chart'   → low confidence, has a guess
        - confident=False, type_label=''            → no classification signal
        """
        import logging
        try:
            annotations = picture.annotations or {}
            classifier = annotations.get('document_figure_classifier', {})
            image_type = classifier.get('class', '')
            confidence = classifier.get('confidence', 0.0)

            logging.debug(
                "Picture classifier: class=%r confidence=%.3f → %s",
                image_type,
                confidence,
                "confident" if (image_type and confidence >= 0.5) else "low-confidence" if image_type else "no-signal",
            )

            if not image_type:
                return ('', False)

            if confidence >= 0.5:
                return (image_type.lower(), True)
            else:
                return (image_type.lower(), False)

        except Exception:
            logging.debug("Picture classifier: failed to extract classification", exc_info=True)
            return ('', False)

    def _picture_to_markdown(self, picture: PictureItem, doc: DoclingDocument) -> str:
        """Convert PictureItem to markdown with VLM description. AC-2.1, AC-2.2, AC-2.3"""
        from siphon_server.config import settings

        if picture is None:
            raise ValueError("Picture is None")

        # Get classification type (AC-2.2: type non-empty)
        image_type, confident = self._get_picture_type(picture)

        # Build directive label: three tiers
        if confident:
            label = image_type                        # e.g. "bar_chart"
        elif image_type:
            label = f"image -- likely {image_type}"  # e.g. "image -- likely bar_chart"
        else:
            label = "image"                           # no signal

        # Skip description if disabled
        if not settings.docling_picture_description_enabled:
            description = f"[Image: {label}]"
        else:
            try:
                description = self._get_vlm_description(picture, doc, image_type)
                if not description or not description.strip():
                    raise ValueError(f"VLM returned empty description for picture type {label}")
            except TimeoutError:
                raise
            except ValueError:
                raise

        markdown = f':::{{{label}}}\n{description}\n:::\n\n'

        return markdown

    def _select_vlm_prompt(self, image_type: str) -> str:
        """Select VLM prompt template based on image classification type."""
        chart_types = {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "box_plot"}
        diagram_types = {"diagram", "flow_chart", "engineering_drawing"}
        ocr_types = {"text"}

        if image_type in chart_types:
            return self.PROMPT_CHART
        elif image_type in diagram_types:
            return self.PROMPT_DIAGRAM
        elif image_type in ocr_types:
            return self.PROMPT_OCR
        else:
            return self.PROMPT_DEFAULT

    def _get_vlm_description(self, picture: PictureItem, doc: DoclingDocument, image_type: str) -> str:
        """Get VLM description for image. AC-2.4"""
        import io
        from siphon_server.config import settings

        pil_image = picture.get_image(doc)
        if pil_image is None:
            raise ValueError(f"Picture lacks image data")

        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        prompt = self._select_vlm_prompt(image_type)

        vlm = VLMClient(
            url=settings.docling_vlm_url,
            model=settings.docling_vlm_model,
            timeout=settings.docling_vlm_timeout,
        )

        description = vlm.describe(image_bytes, prompt)
        return description

    def _docling_convert(self, path: Path) -> DoclingDocument:
        """Convert document to DoclingDocument using Docling."""
        from siphon_server.config import settings
        import os
        # yt-dlp's Cryptodome compat shim conflicts with torch._dynamo's pickle cache.
        # Eager mode is sufficient for inference; dynamo compilation is not needed.
        os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

        # Build pipeline options
        options = PdfPipelineOptions(
            do_ocr=settings.docling_do_ocr,
            do_table_structure=settings.docling_do_table_structure,
            do_picture_classification=settings.docling_do_picture_classification,
            do_picture_description=settings.docling_picture_description_enabled,
            picture_area_threshold=settings.docling_picture_area_threshold,
            generate_picture_images=True,
            enable_remote_services=settings.docling_picture_description_enabled,
            document_timeout=120,
        )

        converter = DocumentConverter(
            format_options={"pdf": PdfFormatOption(pipeline_options=options)}
        )

        try:
            result = converter.convert(path)
            return result.document
        except TimeoutError as e:
            # AC-5.2: Timeout > 120s
            raise TimeoutError(f"Document processing exceeded 120s timeout on {path}") from e
        except FileNotFoundError as e:
            # AC-5.5: Missing model weights
            raise FileNotFoundError(
                f"Docling model weights not found. "
                f"Run: docling-cli download-models"
            ) from e
        except ImportError as e:
            raise ImportError(
                f"Missing dependency for Docling: {e}. "
                f"On headless servers, ensure opencv-python-headless is installed."
            ) from e
        except Exception as e:
            # AC-5.1: Corrupted document
            raise ValueError(f"Corrupted document: {path}. Docling converter failed: {e}") from e

    def _generate_metadata(self, source: SourceInfo) -> dict[str, str]:
        path = Path(source.original_source)
        metadata = FileMetadata(
            file_name=path.name,
            hash=source.hash,
            created_at=self._get_created_at(path),
            last_modified=self._get_last_modified(path),
            file_size=self._get_file_size(path),
            extension=path.suffix.lower(),
            mime_type=self._get_mime_type(path.suffix.lower()),
        )
        return metadata.model_dump()

    def _get_mime_type(self, extension: str) -> str:
        """
        Get MIME type for given extension.
        """
        return MIME_TYPES.get(extension, "application/octet-stream")

    def _get_created_at(self, path: Path) -> str:
        timestamp = path.stat().st_ctime
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.isoformat()

    def _get_last_modified(self, path: Path) -> str:
        """
        Get file last modified timestamp as ISO string.
        """
        timestamp = path.stat().st_mtime
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.isoformat()

    def _get_file_size(self, path: Path) -> int:
        """
        Get file size in bytes.
        """
        return path.stat().st_size
