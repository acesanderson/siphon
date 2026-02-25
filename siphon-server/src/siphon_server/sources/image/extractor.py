from __future__ import annotations

# NOTE: Vision extraction currently delegates to conduit with the default model.
# A dedicated local vision worker is planned for future iterations.

import asyncio
import base64
import urllib.request
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.file_types import MIME_TYPES
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo
from siphon_server.config import settings

PREFERRED_MODEL = settings.default_model
_VISION_PROMPT = (
    "Describe this image in detail. Include the main subject, setting, "
    "notable objects, colors, text visible in the image, and any other "
    "relevant visual information."
)


class ImageExtractor(ExtractorStrategy):
    """Extract content from images using a vision model via conduit."""

    source_type: SourceType = SourceType.IMAGE

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        image_bytes = self._read_bytes(source.original_source)
        ext = Path(source.original_source.split("?")[0]).suffix.lower()
        mime = MIME_TYPES.get(ext, "image/jpeg")
        b64 = base64.b64encode(image_bytes).decode()
        description = asyncio.run(self._describe(b64, mime))
        metadata = {
            "file_name": Path(source.original_source).name,
            "extension": ext,
            "mime_type": mime,
        }
        return ContentData(
            source_type=self.source_type,
            text=description,
            metadata=metadata,
        )

    def _read_bytes(self, source: str) -> bytes:
        if source.startswith("http://") or source.startswith("https://"):
            with urllib.request.urlopen(source) as resp:
                return resp.read()
        return Path(source).read_bytes()

    async def _describe(self, b64_image: str, mime_type: str) -> str:
        from conduit.config import settings as conduit_settings
        from conduit.core.model.model_async import ModelAsync
        from conduit.domain.request.generation_params import GenerationParams

        model = ModelAsync(model=PREFERRED_MODEL)
        params = GenerationParams(model=PREFERRED_MODEL)
        options = conduit_settings.default_conduit_options()
        options.cache = conduit_settings.default_cache(project_name="siphon")

        prompt = f"{_VISION_PROMPT}\n\n<image_base64 mime='{mime_type}'>{b64_image}</image_base64>"
        result = await model.query(query_input=prompt, params=params, options=options)
        return str(result.content)
