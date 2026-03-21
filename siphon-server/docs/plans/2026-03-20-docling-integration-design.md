# Docling Integration Design

**Status:** Design Review
**Author:** Claude
**Date:** 2026-03-20

---

## Goal

Replace MarkItDown with Docling for PDF, DOCX, and PPTX extraction in `DocExtractor`. Produce complete, LLM-ready markdown that captures document structure, embeds VLM-generated image descriptions, marks OCR-recovered text, and routes prompt templates based on image classification.

---

## Constraints and Non-Goals

### Constraints
- **Deployment context:** siphon-server runs ONLY on AlphaBlue, invoked ONLY through HeadwaterServer. VLM endpoint availability is guaranteed by deployment.
- **Fail-fast policy:** No graceful degradation. Corrupted documents, timeouts, OCR failures are hard errors. If any document element cannot be reliably extracted, extraction fails entirely (no partial results).
- **Single model per format:** Use one VLM (minicpm-v:latest) for all images; route prompts based on Docling's picture_classifier output, not model swapping.
- **No image references in output:** Markdown contains no file paths, data URIs, or base64-embedded images. Only VLM descriptions as text.
- **Siphon's markdown philosophy:** Everything convertible to high-fidelity markdown for LLM context. No lossy serialization; all content present in text output.
- **Memory model:** Entire document loaded into memory during extraction. No streaming or chunked processing.

### Non-Goals
- Support partial extraction or best-effort recovery (all-or-nothing)
- Handle missing Docling model weights gracefully (fail loudly with installation instructions)
- Persist DoclingDocument objects or JSON representations (transformer produces markdown only)
- Build a general-purpose Docling wrapper library (siphon-specific adapter only)
- Optimize for text-only documents (latency tradeoff acceptable for complete extraction)
- Support formats outside PDF/DOCX/PPTX via Docling (other sources use existing extractors)
- Image embedding modes (base64, file refs, URLs all explicitly forbidden)
- Performance SLA or latency targets (acceptable range: 1-30s depending on document complexity)
- Character encoding normalization (pass through as Docling provides)
- Streaming large documents or memory-efficient processing
- Backwards compatibility with MarkItDown (direct removal; callers must update)

---

## Interface Contracts

### Public API: `DocExtractor.extract()`

**Signature (unchanged):**
```python
def extract(self, source: SourceInfo) -> ContentData:
    """
    Extract text and metadata from a document source.

    Args:
        source: SourceInfo with original_source as file path

    Returns:
        ContentData with:
            - text: Complete LLM-ready markdown
            - metadata: File metadata (name, size, hash, timestamps, mime_type)
    """
```

**Behavior change:**
- **Input:** Same as before (file path)
- **Output:** Same shape (ContentData), but `text` field is now Docling-based markdown instead of MarkItDown
- **Markdown format:** See "Domain Language" section below

### Internal: `DocExtractor._docling_to_markdown()`

**Signature:**
```python
def _docling_to_markdown(self, doc: DoclingDocument) -> str:
    """
    Transform a DoclingDocument into complete LLM-ready markdown.

    Args:
        doc: DoclingDocument from Docling converter (non-null, post-validation)

    Returns:
        str: Markdown with:
            - Document hierarchy preserved (H1/H2/H3 structure)
            - Tables as GFM pipe syntax (see _table_to_markdown for specs)
            - Code blocks with language identifiers
            - Formulas as LaTeX ($...$)
            - VLM image descriptions wrapped in <image type="...">...</image>
            - OCR-extracted text prefixed with <!-- OCR: from page N -->
            - Lists with proper nesting
            - No file references, data URIs, or image placeholders

    Raises:
        RuntimeError: If doc is None or invalid
        ValueError: If any picture lacks classification or image data
        TimeoutError: If VLM call times out
    """
```

**Detailed Behavior:**

1. **OCR text marking:** Text is marked with `<!-- OCR: from page N -->` iff:
   - Item has provenance with page number
   - Item's source is OCR (detected via Docling's OCR confidence metadata on TextItem)
   - Marker appears once per contiguous OCR block, not per paragraph

2. **Image handling:** Every PictureItem must have:
   - Valid classification from document_figure_classifier (26 categories or 'unknown')
   - Non-null image_data (bytes or PIL Image)
   - VLM description (non-empty string, or error)
   - Classification confidence available (for filtering/defaulting)

3. **Picture markdown format:**
   ```markdown
   <image type="CLASSIFIED_TYPE">
   VLM_DESCRIPTION_TEXT
   </image>
   ```
   - Type is lowercase category from Docling (bar_chart, diagram, photo, etc.)
   - Type defaults to 'unknown' if classification confidence < 0.5 or missing
   - Description must be non-empty (error if VLM returns null/empty)

4. **Tables:** See `_table_to_markdown()` specification below

### Internal: `DocExtractor._table_to_markdown()`

**Signature:**
```python
def _table_to_markdown(self, table: TableItem) -> str:
    """
    Convert TableItem to GFM pipe syntax markdown.

    Args:
        table: DoclingDocument's TableItem

    Returns:
        str: Valid GFM table in markdown format

    Raises:
        ValueError: If table data is malformed or unconvertible
    """
```

**Specifications:**
- Output format: GFM pipe table (pipes, dashes, aligned columns)
- Header row: First row treated as headers (generated if absent)
- Cell content: Plain text only; if cell contains complex markup, flatten to text
- Merged cells: Not supported in GFM; expand merged cell content to all cells in span
- Column width: No column width limits in markdown, but tables with 50+ columns must be flagged (warning log, may produce unreadable output)
- Empty cells: Preserve as empty pipes `| |`
- Cell pipes: If cell text contains `|`, escape as `\|` or fail with clear error
- Newlines in cells: Collapse to space or `<br>` (TBD in implementation)

---

### Internal: VLM Prompt Router

**Conceptual interface (not a formal method):**
```python
# Docling's picture_classifier runs on every image
classification = picture_item.annotations.get('document_figure_classifier', {})

# Extract type and confidence
image_type = classification.get('class', 'unknown')
confidence = classification.get('confidence', 0.0)

# Default to 'unknown' if confidence too low
if confidence < 0.5:
    image_type = 'unknown'

# Route to appropriate prompt based on type
prompt = self._select_vlm_prompt(image_type)

# Call VLM with prompt
description = vlm_client.describe(picture_item.image_data, prompt=prompt)
# Error if description is empty/null (must be non-empty)
```

**Prompts (configuration-driven; loaded from config.py or environment):**
- `text`: OCR extraction (minicpm-v optimized)
- `chart`: Chart/graph analysis (bar_chart, line_chart, pie_chart, scatter_plot)
- `diagram`: Diagram/flowchart interpretation (diagram, flow_chart, engineering_drawing, etc.)
- `default`: Generic image description (for unknown/photo/screenshot/etc.)

**Configuration precedence:** Environment variables → config.py → hardcoded defaults

---

## Acceptance Criteria

### Extraction and Output
- [ ] `DocExtractor.extract()` on valid PDF/DOCX/PPTX returns `ContentData` with `text` field length > 100 characters
- [ ] Returned markdown parses as valid GFM using `github-markdown` parser (no syntax errors, no orphaned pipes/dashes)
- [ ] Document hierarchy is preserved: Heading levels in markdown output match Docling's source (H2 for PDF top-level, H3 for subsections, etc.)
- [ ] Text length in output ≥ 80% of original native text length (accounting for ~20% markdown overhead from formatting)
- [ ] Tables are represented as GFM pipe syntax with header separator row
- [ ] No file paths, URIs (`http://`, `file://`), or base64 strings (`data:image`) in markdown output

### Image Handling
- [ ] For every `PictureItem` in DoclingDocument, markdown contains exactly one `<image type="...">...</image>` block
- [ ] Every `<image>` tag has non-empty `type` attribute from {bar_chart, diagram, photo, ...} or 'unknown'
- [ ] Every `<image>` tag contains non-empty description text (non-null, non-whitespace-only)
- [ ] VLM is called exactly once per image (no redundant calls; no skipped images)
- [ ] If picture_classifier confidence < 0.5, type defaults to 'unknown' (not error)
- [ ] Markdown contains zero `![](...)` image references, zero `<img>` tags, zero base64 data URIs

### OCR and Interpreted Elements
- [ ] Every contiguous block of OCR-extracted text is prefixed with exactly one `<!-- OCR: from page N -->` comment
- [ ] OCR comment appears only for text where Docling's TextItem has OCR confidence metadata (not for all text)
- [ ] If OCR confidence on any page < 0.5, extraction fails with `ValueError` (no silent acceptance of unreadable OCR)
- [ ] Extraction succeeds for documents with mixed native + OCR content (not all-or-nothing per document, but all-or-nothing per page)

### Configuration and VLM Integration
- [ ] `docling_vlm_url` read from environment var `SIPHON_DOCLING_VLM_URL`, then config.py, defaults to `http://localhost:11434/v1/chat/completions`
- [ ] `docling_vlm_model` read from environment var `SIPHON_DOCLING_VLM_MODEL`, then config.py, defaults to `minicpm-v:latest`
- [ ] `docling_picture_description_enabled` read from config/env; when False, VLM is not called (skips description stage)
- [ ] `docling_picture_area_threshold` (default 0.05) is passed to Docling pipeline; images < 5% page area produce no description
- [ ] Prompt template selection: bar_chart/line_chart/pie_chart → `PROMPT_CHART`, diagram/flow_chart → `PROMPT_DIAGRAM`, others → `PROMPT_DEFAULT`

### Error Handling
- [ ] Corrupted PDF/DOCX/PPTX raises `ValueError("Corrupted document: ...")` (extraction stops, no partial results)
- [ ] Document processing > 120s raises `TimeoutError("Document processing exceeded 120s...")` (stops, no partial results)
- [ ] OCR confidence < 0.5 on any page raises `ValueError("OCR text unreadable on page N...")` (stops, no degradation)
- [ ] VLM call timeout raises `TimeoutError` (stops, no fallback to classification-only)
- [ ] Missing Docling model weights raises `FileNotFoundError` with instruction message at first use
- [ ] VLM returns empty/null description raises `ValueError("VLM returned empty description for picture type X")` (no silent empty tags)

### Metadata
- [ ] `ContentData.metadata` keys: file_name, extension, hash, created_at, last_modified, file_size, mime_type (identical to MarkItDown predecessor)
- [ ] Metadata values are identical regardless of whether document used OCR or native text (same structure guarantees)

---

## Error Handling / Failure Modes

### Hard Failures (Extraction Fails)

| Scenario | Error Type | Message | Rationale |
|----------|-----------|---------|-----------|
| Corrupted PDF/DOCX/PPTX (unreadable by Docling) | `ValueError` | `"Corrupted document: {file_path}. Docling converter failed: {reason}"` | Fail fast; no partial extraction |
| Document processing timeout (> 120s) | `TimeoutError` | `"Document processing exceeded 120s timeout: {file_path}. Extraction failed."` | No partial results; user must handle large docs separately |
| OCR text unreadable (low confidence page) | `ValueError` | `"OCR text unreadable on page {N}. Cannot extract readable content."` | Explicit error; no silent skips of corrupted pages |
| VLM description timeout | `TimeoutError` | `"VLM image description timeout on {image_type} (page {N}). AlphaBlue unavailable or overloaded."` | Fail rather than degrade; VLM is a first-class feature |
| Missing Docling model weights | `FileNotFoundError` | `"Docling model weights not found. Expected at {cache_path}. Run: docling-download-models"` | Clear instruction for resolution |

### Non-Recoverable States

The following state mutations must raise `RuntimeError`:
- Calling `_docling_to_markdown()` on a `DoclingDocument` that is `None` or invalid
- Attempting picture description when `docling_picture_description_enabled=False` but image classification suggests description is needed
- Routing to a VLM prompt template that doesn't exist in `self.vlm_prompts`

---

## Code Example: Conventions and Style

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.models.stages.picture_description.picture_description_api_model import (
    PictureDescriptionApiOptions,
)
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import SourceInfo, ContentData
from siphon_api.enums import SourceType
from pathlib import Path


class DocExtractor(ExtractorStrategy):
    """Extract text and metadata from PDF, DOCX, PPTX via Docling."""

    source_type: SourceType = SourceType.DOC

    def extract(self, source: SourceInfo) -> ContentData:
        """Main extraction entrypoint."""
        try:
            doc = self._docling_convert(source)
            text = self._docling_to_markdown(doc)
            metadata = self._generate_metadata(source)
            return ContentData(source_type=self.source_type, text=text, metadata=metadata)
        except (ValueError, TimeoutError, FileNotFoundError) as e:
            # Fail fast; caller handles error
            raise

    def _docling_convert(self, source: SourceInfo) -> DoclingDocument:
        """Convert document via Docling pipeline."""
        path = Path(source.original_source)

        # Build VLM options
        picture_desc_opts = PictureDescriptionApiOptions(
            url=settings.docling_vlm_url,
            model_name=settings.docling_vlm_model,
            timeout=60.0,
            concurrency=2,
        )

        # Build pipeline options
        options = PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=True,
            do_picture_classification=True,
            do_picture_description=settings.docling_picture_description_enabled,
            picture_description_options=picture_desc_opts,
            picture_area_threshold=settings.docling_picture_area_threshold,
            generate_picture_images=True,
            enable_remote_services=True,
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

    def _docling_to_markdown(self, doc: DoclingDocument) -> str:
        """
        Transform DoclingDocument to complete LLM-ready markdown.

        Handles:
        - Document hierarchy (headings, sections)
        - Tables (GFM pipe syntax)
        - VLM image descriptions (wrapped in <image type="...">...</image>)
        - OCR text (prefixed with <!-- OCR: ... -->)
        - Code blocks, formulas, lists, captions
        """
        # Iterate document with Docling's tree structure
        parts = []
        for item, depth in doc.iterate_items(included_content_layers={ContentLayer.BODY}):
            if isinstance(item, SectionHeaderItem):
                heading = "#" * (item.level + 1)  # H2 → ##
                parts.append(f"{heading} {item.text}\n")
            elif isinstance(item, TextItem):
                # Check if this is OCR-recovered text
                if self._is_ocr_text(item):
                    parts.append(f"<!-- OCR: from page {self._get_page_no(item)} -->\n")
                parts.append(f"{item.text}\n")
            elif isinstance(item, TableItem):
                parts.append(self._table_to_markdown(item))
            elif isinstance(item, PictureItem):
                parts.append(self._picture_to_markdown(item))
            elif isinstance(item, CodeItem):
                lang = item.language or ""
                parts.append(f"```{lang}\n{item.text}\n```\n")
            elif isinstance(item, FormulaItem):
                parts.append(f"${item.text}$\n")
            elif isinstance(item, ListItem):
                # Preserve list structure
                bullet = "- " if item.is_bullet else f"{item.index}. "
                parts.append(f"{bullet}{item.text}\n")

        return "".join(parts)

    def _picture_to_markdown(self, picture: PictureItem) -> str:
        """Convert PictureItem to markdown with VLM description."""
        # Get classification
        classification = picture.annotations.get('document_figure_classifier', {})
        image_type = classification.get('class', 'unknown')

        # Get VLM description
        description = self._get_vlm_description(picture, image_type)

        return f'<image type="{image_type}">\n{description}\n</image>\n\n'

    def _get_vlm_description(self, picture: PictureItem, image_type: str) -> str:
        """Call VLM with appropriate prompt for image type."""
        prompt = self._select_vlm_prompt(image_type)

        # Call VLM client (implementation detail, uses settings.docling_vlm_url)
        vlm = VLMClient(
            url=settings.docling_vlm_url,
            model=settings.docling_vlm_model,
            timeout=60.0,
        )

        description = vlm.describe(picture.image_data, prompt=prompt)
        return description

    def _select_vlm_prompt(self, image_type: str) -> str:
        """Select prompt template based on image classification."""
        prompts = {
            "text": self.PROMPT_OCR,
            "bar_chart": self.PROMPT_CHART,
            "line_chart": self.PROMPT_CHART,
            "pie_chart": self.PROMPT_CHART,
            "diagram": self.PROMPT_DIAGRAM,
            "flow_chart": self.PROMPT_DIAGRAM,
            # ... other mappings
            "default": self.PROMPT_DEFAULT,
        }
        return prompts.get(image_type, prompts["default"])

    # Prompt templates (configuration-driven in production)
    PROMPT_OCR = """## INSTRUCTIONS
    Extract all text, tables, headings, and structure from the document image.
    Output clean, valid Markdown. Preserve hierarchy. Do not hallucinate content.
    ..."""

    PROMPT_CHART = """## INSTRUCTIONS
    Analyze this chart and extract key data, trends, and insights.
    ..."""

    PROMPT_DIAGRAM = """## INSTRUCTIONS
    Describe this diagram, flowchart, or technical drawing.
    ..."""

    PROMPT_DEFAULT = """Describe this image."""

    def _is_ocr_text(self, item: TextItem) -> bool:
        """Check if text was recovered via OCR."""
        # Look for OCR confidence metadata from Docling
        return hasattr(item, 'ocr_confidence') and item.ocr_confidence is not None

    def _get_page_no(self, item: NodeItem) -> int:
        """Extract page number from provenance."""
        if item.prov:
            return item.prov[0].page_no
        return 0

    def _table_to_markdown(self, table: TableItem) -> str:
        """Convert table to GFM pipe syntax."""
        # Implementation uses table.data structure
        # Returns: "| Header | ...\n|---|---\n| Data |...\n\n"
        pass

    def _generate_metadata(self, source: SourceInfo) -> dict[str, str]:
        """Generate file metadata (unchanged from MarkItDown version)."""
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
```

---

## Domain Language

**Exact nouns the implementation uses:**

| Term | Definition | Usage |
|------|-----------|-------|
| **Interpreted element** | Content inferred/generated by a model, not native to the document | VLM image descriptions, OCR-recovered text. Marked with XML tags or comments. |
| **VLM description** | Natural language text generated by the Vision Language Model for an image | Placed inside `<image type="...">description</image>` tags. |
| **Picture classification** | Docling's document_figure_classifier output; categorical prediction of image type (chart, diagram, photo, etc.) | Used to route image to appropriate VLM prompt template. Type value in `<image type="...">`. |
| **OCR text** | Text extracted from image-based/scanned pages via Optical Character Recognition | Prefixed with `<!-- OCR: ... -->` comment. Marked as interpreted because inferred by model. |
| **Docling document** | `DoclingDocument` object; complete structured representation of a document from Docling converter | Internal representation; not persisted or returned to caller. |
| **Complete markdown** | Markdown string containing all document content (text, tables, code, formulas, images, captions) with interpreted elements marked | Final output in `ContentData.text`. Suitable for LLM context. |
| **Picture item** | `PictureItem` from Docling; represents an image/figure/diagram in the document | Contains image data, classifications, VLM-generated descriptions. |
| **Content layer** | Docling's classification of text location; BODY (main content) vs. FURNITURE (headers/footers) | Default iteration uses BODY only; FURNITURE filtered out unless explicitly requested. |

---

## Observability and Instrumentation

### Logging Requirements

**Log levels and events:**
- `INFO`: Extraction started (file path, size), extraction completed (total time, result size)
- `DEBUG`: Docling converter initialized, OCR stage started/completed, VLM call for each image, transformer stage timing
- `WARNING`: Document > 50 columns (table readability), classifier confidence < 0.5 (defaulting to 'unknown'), large markdown output (> 1MB)
- `ERROR`: Corruption detected, timeouts, OCR unreadable, VLM failures, missing weights

**Structured logging format (JSON):**
```json
{
  "level": "INFO",
  "timestamp": "2026-03-20T10:30:45Z",
  "event": "extraction_complete",
  "file_path": "/path/to/doc.pdf",
  "file_size_bytes": 2048576,
  "extraction_time_ms": 3500,
  "output_size_bytes": 145000,
  "images_extracted": 12,
  "ocr_used": true,
  "error": null
}
```

### Metrics to Emit

**Per-extraction metrics:**
- `docling.extraction.duration_ms` — Total extraction time
- `docling.extraction.output_size_bytes` — Markdown output size
- `docling.extraction.images_count` — Number of pictures extracted
- `docling.extraction.ocr_ratio` — Fraction of text from OCR (0.0 to 1.0)
- `docling.extraction.success` — Counter (1 for success, 0 for failure)

**VLM metrics:**
- `docling.vlm.call_count` — Number of VLM calls per extraction
- `docling.vlm.duration_ms` — Per-call latency, tagged by image_type (chart, diagram, photo, etc.)
- `docling.vlm.timeout_count` — Number of timeouts
- `docling.vlm.empty_response_count` — Number of empty descriptions

**Docling metrics:**
- `docling.classifier.distribution` — Histogram of classification types (bar_chart: N, diagram: M, photo: K, etc.)
- `docling.classifier.low_confidence_count` — Images defaulted to 'unknown' due to confidence < 0.5

**Error metrics:**
- `docling.error.corruption_count` — Documents that failed to parse
- `docling.error.timeout_count` — Documents that exceeded 120s
- `docling.error.ocr_unreadable_count` — Documents failing OCR confidence check

### Tracing and Debugging

**Request context:**
- Include document hash (`source.hash`) in all logs for correlation
- Include unique extraction ID for tracing through pipeline stages

**Debug instrumentation:**
- Log Docling pipeline configuration (which options enabled, thresholds) at start
- Log classifier output (type, confidence) for every image
- Log VLM prompt used and first/last 100 chars of response (for debugging poor descriptions)
- Log OCR confidence scores per page (to identify problematic pages)

**Example debug log:**
```json
{
  "level": "DEBUG",
  "event": "vlm_call",
  "image_index": 5,
  "image_type": "bar_chart",
  "classifier_confidence": 0.92,
  "prompt_template": "PROMPT_CHART",
  "vlm_duration_ms": 1240,
  "response_length": 145
}
```

### Production Alerts

- Alert if extraction error rate > 5% over 1 hour (indicates deployment issue)
- Alert if VLM timeout rate > 10% (AlphaBlue overloaded)
- Alert if average extraction latency > 10s (performance degradation)
- Alert if OCR unreadable rate > 20% (document quality issue or OCR model regression)

---

## Invalid State Transitions

**The following state mutations must raise errors:**

1. **Calling `_docling_to_markdown()` with None or invalid DoclingDocument**
   - Error: `RuntimeError("DoclingDocument is None or invalid")`
   - Reason: Document must be successfully parsed before transformation

2. **PictureItem without classification annotation**
   - Error: `ValueError("Picture lacks classification annotation")`
   - Reason: Every image must be classified; indicates Docling pipeline misconfiguration

3. **PictureItem without image_data**
   - Error: `ValueError("Picture lacks image data at index N")`
   - Reason: Cannot call VLM without image bytes; indicates corruption or Docling extraction failure

4. **VLM returns empty or null description**
   - Error: `ValueError("VLM returned empty description for image type XXXX")`
   - Reason: Description must be non-empty; null indicates VLM failure or timeout

5. **Attempting VLM call when `docling_picture_description_enabled=False`**
   - Error: `RuntimeError("Picture description is disabled but reached VLM stage")`
   - Reason: Indicates logic error in transformation flow

6. **Image type maps to non-existent prompt template**
   - Error: `KeyError("Prompt template missing for image type 'XXXX'")`
   - Reason: All Docling classifier types must have a prompt; indicates incomplete configuration

7. **OCR confidence < 0.5 on any page**
   - Error: `ValueError("OCR confidence {score} < 0.5 on page N; text unreadable")`
   - Reason: Unreadable OCR is a hard failure; no graceful degradation

8. **VLM call timeout**
   - Error: `TimeoutError("VLM description timeout for {image_type} on page N (AlphaBlue unavailable?)")`
   - Reason: Fail fast; no fallback to classification-only

9. **Document processing timeout (> 120s)**
   - Error: `TimeoutError("Docling processing exceeded 120s timeout on {file_path}")`
   - Reason: Hard limit to prevent runaway processes

10. **Docling model weights missing at startup**
    - Error: `FileNotFoundError("Docling model weights not found at {cache_path}. Run: docling-cli download-models")`
    - Reason: Clear error with remediation instruction

11. **Corrupted document detected by Docling**
    - Error: `ValueError("Corrupted document: {file_path}. Docling converter failed: {reason}")`
    - Reason: Unrecoverable; fail extraction

12. **Picture.image_data format unexpected (not bytes or PIL Image)**
    - Error: `TypeError("Unexpected image_data type {type}; expected bytes or PIL Image")`
    - Reason: Implementation assumption violated; indicates Docling API change

---

## Implementation Notes

### Critical Clarifications

**OCR text detection:**
- Check for OCR confidence metadata on `TextItem` via `item.metadata` or similar (verify Docling API during implementation)
- OCR marker appears once per contiguous OCR-extracted block, not per paragraph
- Strategy: Track previous item's OCR state; emit comment only when transitioning from non-OCR to OCR

**Prompt template storage:**
- Load from `config.py` as string fields or from separate YAML/JSON file
- Must be environment-variable overridable (e.g., `SIPHON_DOCLING_PROMPT_CHART`)
- Defaults hard-coded as fallback if config missing
- See code example prompts in "Code Example" section

**VLM image_data extraction:**
- Implementation must verify `PictureItem` API: how to extract raw image bytes/PIL Image
- May need to use `picture.get_image()` or access internal `_image` field
- Test early in implementation to avoid surprises

**Table markdown edge cases:**
- Cells containing pipes: escape as `\|`
- Merged cells: expand content to all cells in span (GFM has no merge syntax)
- Wide tables (50+ columns): log warning; may produce unreadable markdown but still valid
- Empty table: still produce valid GFM (headers with no rows is valid)

### Configuration Changes
Expand `config.py` `Settings` dataclass to include:
```python
# VLM backend
docling_vlm_url: str = "http://localhost:11434/v1/chat/completions"
docling_vlm_model: str = "minicpm-v:latest"
docling_vlm_timeout: float = 60.0
docling_vlm_concurrency: int = 2

# Pipeline features
docling_picture_description_enabled: bool = True
docling_picture_area_threshold: float = 0.05
docling_do_ocr: bool = True
docling_do_table_structure: bool = True
docling_do_picture_classification: bool = True

# Prompts (load from separate file or as strings)
docling_prompt_ocr: str = "..."  # or load from resources/
docling_prompt_chart: str = "..."
docling_prompt_diagram: str = "..."
docling_prompt_default: str = "..."
```

Environment variable precedence: `SIPHON_DOCLING_*` overrides config.py, which overrides hardcoded defaults.

### Dependency Changes
- Remove: `markitdown[all]` from `pyproject.toml`
- Add: `docling>=2.0.0`

### File Changes
- `src/siphon_server/sources/doc/extractor.py`: Complete refactor (remove MarkItDown, add Docling converter + transformer)
- `src/siphon_server/config.py`: Add Docling configuration fields
- `src/siphon_server/sources/doc/file_context.py`: No changes needed (routing remains unchanged; files still identified by extension)
- `src/siphon_server/sources/doc/parser.py`: No changes needed (Parser layer unaffected)
- `src/siphon_server/sources/doc/enricher.py`: No changes needed (Enricher receives markdown, not source)
- `pyproject.toml`: Dependency swap

### Testing Strategy
- **Unit tests:**
  - `_docling_to_markdown()` with mock DoclingDocument (text, tables, images, OCR)
  - `_table_to_markdown()` with edge cases (wide tables, merged cells, empty tables)
  - `_select_vlm_prompt()` with each image type
  - `_is_ocr_text()` with various metadata states

- **Integration tests:**
  - Real PDFs (text-heavy, image-heavy, mixed, scanned)
  - Real DOCX and PPTX files
  - Error cases: corrupted files, VLM timeouts (mock), OCR failures
  - Markdown syntax validation (GFM parser)
  - Image extraction and description quality (visual inspection)

- **Performance tests:**
  - Large documents (100+ pages) for memory/time behavior
  - Wide tables (50+ columns) for markdown output quality

- **Configuration tests:**
  - Environment variable precedence
  - Disabled picture description (`enabled=False` skips VLM calls)

