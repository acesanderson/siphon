from __future__ import annotations

import base64
import urllib.request
from pathlib import Path
from typing import override

from siphon_api.enums import SourceType
from siphon_api.file_types import MIME_TYPES
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo

VLM_MODEL = "minicpm-v:latest"
_VISION_PROMPT = """\
Look at this image. First determine what type of image it is, then respond accordingly:

- Text / document / screenshot with text: extract all text verbatim, preserving structure and layout
- Chart, graph, or diagram: describe what it shows — axes, labels, key data points, and the main insight
- Table: extract the data as a markdown table
- Photo or natural image: describe what you see in detail
- Map: describe the geography, locations, and any labels
- UI screenshot or interface: describe the layout and content of the interface
- Icon or logo: identify and describe it

Respond with only the extracted content or description. No preamble, no labels, no explanation of what you did.\
"""


class ImageExtractor(ExtractorStrategy):
    """Extract content from images using minicpm-v via HeadwaterClient."""

    source_type: SourceType = SourceType.IMAGE

    @override
    def extract(self, source: SourceInfo, diarize: bool = False) -> ContentData:
        image_bytes = self._read_bytes(source.original_source)
        ext = Path(source.original_source.split("?")[0]).suffix.lower()
        mime = MIME_TYPES.get(ext, "image/jpeg")
        b64 = base64.b64encode(image_bytes).decode()
        description = self._describe(b64)
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

    def _describe(self, b64_image: str) -> str:
        from conduit.domain.message.message import ImageContent, TextContent, UserMessage
        from conduit.domain.request.generation_params import GenerationParams
        from conduit.domain.request.request import GenerationRequest
        from conduit.domain.config.conduit_options import ConduitOptions
        from headwater_client.client.headwater_client import HeadwaterClient

        image_content = ImageContent(url=f"data:image/png;base64,{b64_image}")
        text_content = TextContent(text=_VISION_PROMPT)
        user_message = UserMessage(content=[image_content, text_content])
        params = GenerationParams.defaults(VLM_MODEL)
        options = ConduitOptions(project_name="siphon")
        request = GenerationRequest(
            messages=[user_message],
            params=params,
            options=options,
        )
        client = HeadwaterClient()
        response = client.conduit.query_generate(request)
        return str(response)
