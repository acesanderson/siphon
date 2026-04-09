from siphon_server.config import settings
from siphon_api.models import ContentData
from conduit.core.model.model_remote import RemoteModelAsync
import json
import asyncio

PREFERRED_MODEL = settings.default_model


async def count_tokens_async(content: ContentData) -> int:
    """Async version of token counting using new Conduit API."""
    model = RemoteModelAsync(model=PREFERRED_MODEL)
    metadata = json.dumps(content.metadata)
    text = content.text
    input_text = metadata + "\n" + text
    tokens = await model.tokenize(input_text)
    return tokens


def count_tokens(content: ContentData) -> int:
    """Sync wrapper for backward compatibility."""
    return asyncio.run(count_tokens_async(content))
