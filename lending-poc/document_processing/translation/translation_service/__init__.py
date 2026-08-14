"""
Translation Service
-------------------
A model-swappable document translation service for legal OCR output.

Quickstart (programmatic use):
    from translation_service.translator import TranslationService
    from translation_service import config

    service = TranslationService(
        kb_path=config.KB_PATH,
        adapter_name=config.MODEL_ADAPTER,
        model_name=config.MODEL_NAME,
        model_options=config.MODEL_OPTIONS,
    )
    translated = service.translate(source_text)
"""

from .translator import TranslationService

__all__ = ["TranslationService"]
