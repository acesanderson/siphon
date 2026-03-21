from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import SourceInfo, ContentData
from siphon_api.enums import SourceType
from siphon_api.metadata import FileMetadata
from siphon_api.file_types import MIME_TYPES
from datetime import datetime, timezone
from markitdown import MarkItDown
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
)


class DocExtractor(ExtractorStrategy):
    """
    Extract content from Doc: i.e. .doc, .docx files.
    """

    source_type: SourceType = SourceType.DOC

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        text = self._extract(source)
        metadata = self._generate_metadata(source)
        return ContentData(source_type=self.source_type, text=text, metadata=metadata)

    def _extract(self, source: SourceInfo) -> str:
        """Extract markdown text from document."""
        path = Path(source.original_source)

        # Docling convert
        doc = self._docling_convert(path)

        # Transform to markdown using core transformer
        markdown = self._docling_to_markdown(doc)

        return markdown

    def _docling_to_markdown(self, doc: DoclingDocument) -> str:
        """Transform DoclingDocument to LLM-ready markdown."""
        if doc is None:
            raise RuntimeError("DoclingDocument is None or invalid")

        parts = []

        # Iterate document content
        for item, depth in doc.iterate_items(included_content_layers={ContentLayer.BODY}):
            if isinstance(item, SectionHeaderItem):
                # Create heading: level determines # count
                heading_level = max(2, getattr(item, 'level', 2) + 1)
                heading_marker = "#" * heading_level
                parts.append(f"{heading_marker} {item.text}\n\n")

            elif isinstance(item, CodeItem):
                # Code block with language identifier
                # Note: Check CodeItem before TextItem since CodeItem is a subclass of TextItem
                lang = getattr(item, 'language', '')
                parts.append(f"```{lang}\n{item.text}\n```\n\n")

            elif isinstance(item, FormulaItem):
                # Mathematical formula in LaTeX format
                # Note: Check FormulaItem before TextItem since FormulaItem is a subclass of TextItem
                parts.append(f"${item.text}$\n\n")

            elif isinstance(item, ListItem):
                # List item (bullet or numbered)
                # Note: Check ListItem before TextItem since ListItem is a subclass of TextItem
                is_bullet = getattr(item, 'is_bullet', True)
                bullet_marker = "-" if is_bullet else f"{getattr(item, 'index', 1)}."
                parts.append(f"{bullet_marker} {item.text}\n")

            elif isinstance(item, TableItem):
                # GFM pipe table
                parts.append(self._table_to_markdown(item))

            elif isinstance(item, TextItem):
                # Simple text paragraph
                parts.append(f"{item.text}\n\n")

        return "".join(parts)

    def _table_to_markdown(self, table: TableItem) -> str:
        """Convert TableItem to GFM pipe table."""
        if not hasattr(table, 'data') or not table.data:
            raise ValueError(f"Table lacks data")

        rows = table.data
        if not rows or not rows[0]:
            raise ValueError("Empty table")

        markdown_lines = []

        for i, row in enumerate(rows):
            cells = []
            for cell_content in row:
                cell_text = str(cell_content).replace("|", "\\|")
                cells.append(cell_text)

            markdown_lines.append("| " + " | ".join(cells) + " |")

            if i == 0:
                separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                markdown_lines.append(separator)

        if len(rows[0]) > 50:
            import logging
            logging.warning(f"Wide table detected: {len(rows[0])} columns.")

        return "\n".join(markdown_lines) + "\n\n"

    def _docling_convert(self, path: Path) -> DoclingDocument:
        """Convert document to DoclingDocument using Docling."""
        from siphon_server.config import settings

        # Build pipeline options
        options = PdfPipelineOptions(
            do_ocr=settings.docling_do_ocr,
            do_table_structure=False,  # Disabled for now; requires additional system libs
            do_picture_classification=False,  # Disabled for now; requires CV2
            do_picture_description=False,  # Disable for now; Phase 5 enables
            picture_area_threshold=settings.docling_picture_area_threshold,
            generate_picture_images=False,
            enable_remote_services=False,  # No VLM yet
            document_timeout=120,
        )

        converter = DocumentConverter(
            format_options={"pdf": PdfFormatOption(pipeline_options=options)}
        )

        try:
            result = converter.convert(path)
            return result.document
        except Exception as e:
            raise ValueError(f"Corrupted document: {path}. Docling converter failed: {e}")

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
