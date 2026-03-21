# Docling Integration Spec

**Status:** Proposed
**Scope:** `sources/doc` — replaces `markitdown` for PDF, DOCX, PPTX

---

## Problem

Markitdown is a text-layer extractor. It works well for DOCX and PPTX files that are
primarily text, but silently drops embedded images. For image-heavy documents — scanned
PDFs, slide decks, whitepapers with figures — the extracted text is sparse or meaningless.

There is no reliable way to detect "image-heavy" at the document level and branch to a
different pipeline, because real documents are mixed: some pages are text, some are
diagrams, some are tables. A per-document gate misses this.

## Solution

Replace markitdown with [Docling](https://github.com/DS4SD/docling) for PDF, DOCX, and
PPTX processing. Docling processes documents at the element level: each text block, table,
figure, formula, and code block is identified separately and routed through the appropriate
model. Embedded images above a configurable size threshold are described by a VLM.

This eliminates:
- The need to detect image-heavy documents before choosing a path
- The DOCX/PPTX → PDF conversion step (Docling reads Office formats natively)
- Silent information loss on image content

## What Docling Does

### Pipeline stages (StandardPdfPipeline)

1. **Layout analysis** — Heron model identifies element types and bounding boxes per page
2. **OCR** — RapidOCR (default) or Tesseract for scanned/image pages
3. **Table structure** — Reconstructs table row/column structure
4. **Picture classification** — Classifies each embedded image (diagram, chart, logo, etc.)
5. **Picture description** — VLM describes images that pass size and classification filters

### Picture description filtering

The description stage has two built-in filters that prevent wasting VLM calls on
decorative content:

- `picture_area_threshold` (default `0.05`): skips images smaller than 5% of page area
- `classification_allow` / `classification_deny`: filter by classified picture type
- `classification_min_confidence`: skip low-confidence classifications

### Output

`result.document.export_to_markdown()` — clean markdown with prose text in reading order,
tables as markdown tables, and VLM image descriptions as inline text blocks. This is a
drop-in replacement for `MarkItDown.convert(path).text_content`.

## Scope

| Format | Before | After |
|--------|--------|-------|
| `.pdf` | markitdown (text layer only) | Docling (OCR + picture description) |
| `.docx` | markitdown | Docling |
| `.pptx` | markitdown | Docling |
| `.txt`, `.md` | raw read | raw read (unchanged) |
| `.csv`, `.json` | raw read | raw read (unchanged) |
| Code files | raw read | raw read (unchanged) |
| Images (standalone) | conduit VLM | conduit VLM (unchanged) |
| Audio/Video | whisper pipeline | whisper pipeline (unchanged) |

The `Extensions["markitdown"]` category in `file_context.py` should be split: a `docling`
set for PDF/DOCX/PPTX, and the remainder handled by raw reads. The markitdown dependency
can then be removed entirely.

## Configuration

### VLM backend

Picture description requires an OpenAI-compatible chat completions endpoint. Point this at
Ollama on AlphaBlue — never run inference locally on the MacBook:

```python
from docling.models.stages.picture_description.picture_description_api_model import (
    PictureDescriptionApiOptions,
)

picture_description_options = PictureDescriptionApiOptions(
    url="http://alphaBlue:11434/v1/chat/completions",
    model_name="qwen2.5vl:7b",
    timeout=60.0,
    concurrency=2,
)
```

`enable_remote_services=True` must be set on the pipeline options when using the API
backend.

### Recommended pipeline options

```python
from docling.datamodel.pipeline_options import PdfPipelineOptions

options = PdfPipelineOptions(
    do_ocr=True,
    do_table_structure=True,
    do_picture_classification=True,
    do_picture_description=True,
    picture_description_options=picture_description_options,
    generate_picture_images=True,  # required for description to work
    enable_remote_services=True,
    document_timeout=120,
)
```

For DOCX/PPTX, use `WordFormatOption` / `PowerpointFormatOption` with equivalent
enrichment settings. Picture classification and description run identically on embedded
images regardless of source format.

### Area threshold

The default `picture_area_threshold=0.05` (5% of page area) filters out logos and
decorative icons while catching diagrams and figures. Calibrate against a real document
sample from actual siphon usage before shipping.

## Changes Required

### `pyproject.toml`

Replace `markitdown[all]` with `docling`:

```toml
dependencies = [
    "docling>=2.0.0",
    # markitdown[all]  <- remove
    ...
]
```

Docling is a heavy install (~100 transitive packages including torch, transformers,
opencv). This is appropriate for siphon-server which already carries ML dependencies.

### `sources/doc/extractor.py`

Replace the `MarkItDown` call in `DocExtractor._extract()`:

```python
# Before
from markitdown import MarkItDown

def _extract(self, source: SourceInfo) -> str:
    md = MarkItDown()
    return md.convert(Path(source.original_source)).text_content

# After
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions

def _extract(self, source: SourceInfo) -> str:
    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=_build_pipeline_options())}
    )
    result = converter.convert(source.original_source)
    return result.document.export_to_markdown()
```

`_build_pipeline_options()` should read the VLM endpoint and model from
`siphon_server.config.settings` so they are configurable without code changes.

### `config.py`

Add:

```python
docling_vlm_url: str = "http://localhost:11434/v1/chat/completions"
docling_vlm_model: str = "qwen2.5vl:7b"
docling_picture_area_threshold: float = 0.05
docling_picture_description_enabled: bool = True
```

`docling_picture_description_enabled` allows disabling the VLM call (falling back to
classification-only) when AlphaBlue is unavailable.

### `sources/doc/file_context.py`

The `convert_markitdown()` function and its routing case should be replaced or split.
Docling handles the formats markitdown was responsible for; the remaining formats in that
category (if any) route to raw reads.

## First-Run Behaviour

Docling downloads layout and classification model weights from HuggingFace on first use,
cached in `~/.cache/docling/` (or `$HF_HOME`). Approximate sizes:

- Heron layout model: ~100MB
- Document picture classifier: ~80MB
- RapidOCR: ~15MB (bundled)

The VLM (Qwen2.5-VL) runs on AlphaBlue via Ollama — no weights downloaded on the
siphon-server host for that component.

## Operational Notes

- **Latency**: Docling is slower than markitdown for text-only documents. A 10-page text
  PDF: markitdown ~0.1s, Docling ~1–3s (layout model overhead). Image-heavy pages with
  VLM description add ~5–15s per image page depending on AlphaBlue throughput.
- **Batching**: `layout_batch_size` and `ocr_batch_size` default to 4 pages. Increase on
  AlphaBlue if GPU memory allows.
- **PPTX fidelity**: No LibreOffice required. Embedded charts are extracted as images and
  described by the VLM.

## Open Questions

1. Should VLM image descriptions be stored separately in `ContentData.metadata` (as a
   list of `{"page": N, "description": "..."}`) in addition to inline in the markdown?
   This would allow downstream enrichment to distinguish VLM-generated content from
   native text.

2. For Drive sources (Google Docs/Slides exported as DOCX/PPTX), should the Drive
   extractor export to these formats and hand off to the Docling path, or maintain a
   separate extraction path? The Docling path is preferred for consistency, but depends
   on the Drive extractor completing its WIP export logic first.
