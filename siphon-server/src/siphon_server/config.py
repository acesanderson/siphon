import tomllib
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Settings:
    default_model: str
    log_level: int
    cache: bool
    # Docling VLM configuration
    docling_vlm_url: str = "http://localhost:11434/v1/chat/completions"
    docling_vlm_model: str = "minicpm-v:latest"
    docling_vlm_timeout: float = 60.0
    docling_vlm_concurrency: int = 2
    docling_picture_description_enabled: bool = True
    docling_picture_area_threshold: float = 0.05
    docling_do_ocr: bool = True
    docling_do_table_structure: bool = True
    docling_do_picture_classification: bool = True


def load_settings() -> Settings:
    """Load settings with precedence: ENV VARS > config file > defaults"""

    # Defaults (lowest priority)
    config = {
        "default_model": "gemma4:latest",
        "log_level": 2,
        "cache": True,
        # Docling defaults
        "docling_vlm_url": "http://localhost:11434/v1/chat/completions",
        "docling_vlm_model": "minicpm-v:latest",
        "docling_vlm_timeout": 60.0,
        "docling_vlm_concurrency": 2,
        "docling_picture_description_enabled": True,
        "docling_picture_area_threshold": 0.05,
        "docling_do_ocr": True,
        "docling_do_table_structure": True,
        "docling_do_picture_classification": True,
    }

    # Load from config file if it exists
    config_path = Path.home() / ".config" / "siphon" / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            file_config = tomllib.load(f)
            config.update(file_config)

    # Override with environment variables (highest priority)
    env_mappings = {
        "SIPHON_DEFAULT_MODEL": "default_model",
        "SIPHON_LOG_LEVEL": "log_level",
        "SIPHON_CACHE": "cache",
        "SIPHON_DOCLING_VLM_URL": "docling_vlm_url",
        "SIPHON_DOCLING_VLM_MODEL": "docling_vlm_model",
        "SIPHON_DOCLING_VLM_TIMEOUT": "docling_vlm_timeout",
        "SIPHON_DOCLING_VLM_CONCURRENCY": "docling_vlm_concurrency",
        "SIPHON_DOCLING_PICTURE_DESCRIPTION_ENABLED": "docling_picture_description_enabled",
        "SIPHON_DOCLING_PICTURE_AREA_THRESHOLD": "docling_picture_area_threshold",
        "SIPHON_DOCLING_DO_OCR": "docling_do_ocr",
        "SIPHON_DOCLING_DO_TABLE_STRUCTURE": "docling_do_table_structure",
        "SIPHON_DOCLING_DO_PICTURE_CLASSIFICATION": "docling_do_picture_classification",
    }

    for env_var, config_key in env_mappings.items():
        if env_var in os.environ:
            value = os.environ[env_var]
            # Type coercion
            if config_key in ["docling_picture_description_enabled", "docling_do_ocr",
                             "docling_do_table_structure", "docling_do_picture_classification", "cache"]:
                config[config_key] = value.lower() in ("true", "1", "yes")
            elif config_key in ["docling_vlm_timeout", "docling_picture_area_threshold"]:
                config[config_key] = float(value)
            elif config_key in ["docling_vlm_concurrency", "log_level"]:
                config[config_key] = int(value)
            else:
                config[config_key] = value

    return Settings(**config)


# Singleton
settings = load_settings()
