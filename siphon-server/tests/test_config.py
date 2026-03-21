import os
import pytest


def test_docling_config_defaults():
    """Test Docling configuration defaults when env vars absent."""
    # Remove env vars if set
    for key in ['SIPHON_DOCLING_VLM_URL', 'SIPHON_DOCLING_VLM_MODEL',
                'SIPHON_DOCLING_PICTURE_DESCRIPTION_ENABLED',
                'SIPHON_DOCLING_PICTURE_AREA_THRESHOLD']:
        os.environ.pop(key, None)

    # Reload config (may need to clear module cache)
    import importlib
    import sys

    # Remove from cache to force reload
    if 'siphon_server.config' in sys.modules:
        del sys.modules['siphon_server.config']

    import siphon_server.config as config_module
    importlib.reload(config_module)

    settings = config_module.load_settings()

    # Assertions
    assert settings.docling_vlm_url == "http://localhost:11434/v1/chat/completions"
    assert settings.docling_vlm_model == "minicpm-v:latest"
    assert settings.docling_picture_description_enabled == True
    assert settings.docling_picture_area_threshold == 0.05
