import os
import pytest
import importlib
import sys


def _reload_config():
    """Helper to reload the config module."""
    if 'siphon_server.config' in sys.modules:
        del sys.modules['siphon_server.config']
    import siphon_server.config as config_module
    importlib.reload(config_module)
    return config_module


def test_docling_config_defaults():
    """Test Docling configuration defaults when env vars absent."""
    # Remove env vars if set
    for key in ['SIPHON_DOCLING_VLM_URL', 'SIPHON_DOCLING_VLM_MODEL',
                'SIPHON_DOCLING_PICTURE_DESCRIPTION_ENABLED',
                'SIPHON_DOCLING_PICTURE_AREA_THRESHOLD']:
        os.environ.pop(key, None)

    config_module = _reload_config()
    settings = config_module.load_settings()

    # Assertions
    assert settings.docling_vlm_url == "http://localhost:11434/v1/chat/completions"
    assert settings.docling_vlm_model == "minicpm-v:latest"
    assert settings.docling_picture_description_enabled == True
    assert settings.docling_picture_area_threshold == 0.05


def test_environment_variable_override_vlm_url():
    """Test: SIPHON_DOCLING_VLM_URL overrides config. AC-4.1"""
    os.environ['SIPHON_DOCLING_VLM_URL'] = 'http://custom-vlm:5000'

    try:
        config_module = _reload_config()
        settings = config_module.load_settings()
        assert settings.docling_vlm_url == 'http://custom-vlm:5000'
    finally:
        del os.environ['SIPHON_DOCLING_VLM_URL']
        _reload_config()


def test_environment_variable_override_vlm_model():
    """Test: SIPHON_DOCLING_VLM_MODEL overrides config. AC-4.2"""
    os.environ['SIPHON_DOCLING_VLM_MODEL'] = 'custom-model:latest'

    try:
        config_module = _reload_config()
        settings = config_module.load_settings()
        assert settings.docling_vlm_model == 'custom-model:latest'
    finally:
        del os.environ['SIPHON_DOCLING_VLM_MODEL']
        _reload_config()


def test_config_picture_description_toggle():
    """Test: picture_description_enabled toggles VLM. AC-4.3"""
    os.environ['SIPHON_DOCLING_PICTURE_DESCRIPTION_ENABLED'] = 'false'

    try:
        config_module = _reload_config()
        settings = config_module.load_settings()
        assert settings.docling_picture_description_enabled == False
    finally:
        del os.environ['SIPHON_DOCLING_PICTURE_DESCRIPTION_ENABLED']
        _reload_config()


def test_config_picture_area_threshold():
    """Test: picture_area_threshold configurable. AC-4.4"""
    os.environ['SIPHON_DOCLING_PICTURE_AREA_THRESHOLD'] = '0.1'

    try:
        config_module = _reload_config()
        settings = config_module.load_settings()
        assert settings.docling_picture_area_threshold == 0.1
    finally:
        del os.environ['SIPHON_DOCLING_PICTURE_AREA_THRESHOLD']
        _reload_config()
