# MarkItDown → Docling Migration

## Summary

DocExtractor has been refactored to use Docling instead of MarkItDown for PDF, DOCX, and PPTX extraction. This provides:

- **Better image handling:** Embedded images are described via VLM, not silently dropped
- **OCR support:** Scanned documents and mixed native+OCR content are fully extracted
- **Markdown quality:** Complete, LLM-ready markdown with proper structure preservation

## Configuration

New settings in `config.py`:

```python
docling_vlm_url = "http://localhost:11434/v1/chat/completions"  # Ollama endpoint
docling_vlm_model = "minicpm-v:latest"  # Vision model
docling_picture_description_enabled = True  # Toggle VLM calls
docling_picture_area_threshold = 0.05  # Skip trivial images
```

Override with environment variables: `SIPHON_DOCLING_*`

## Breaking Changes

- MarkItDown is no longer a dependency
- Extraction output is Docling-based markdown (may differ slightly from MarkItDown)
- VLM availability required (runs on AlphaBlue only)

## Error Handling

- Corrupted documents: `ValueError` with clear message
- Timeouts (>120s): `TimeoutError`
- Unreadable OCR: `ValueError` with page number
- Missing model weights: `FileNotFoundError` with install instructions

All errors fail-fast; no partial extraction.
