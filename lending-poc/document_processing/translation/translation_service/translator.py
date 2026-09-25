"""
translator.py — TranslationService: the main orchestrator.

Wires together:
  - KB loader + retriever  (domain-specific terminology context)
  - Model adapter          (LLM backend)
  - Prompt template        (from config)

Domain is set at instantiation time. A separate service instance is needed
per domain — or pass domain="banking" / domain="legal" when constructing.
"""

from pathlib import Path

from . import config as _cfg
from .adapters import ADAPTERS
from .adapters.base import ModelAdapter
from .kb.loader import load_kb
from .kb.retriever import retrieve, format_terminology_block


class TranslationService:
    """
    Translates OCR text from Marathi (or other Indic languages) to English
    using domain-specific terminology from the knowledge base.

    Args:
        domain:          "banking" or "legal" (default: config.DEFAULT_DOMAIN)
        kb_path:         explicit KB path — overrides domain-based lookup
        adapter_name:    key into the ADAPTERS registry (default: config.MODEL_ADAPTER)
        model_name:      model identifier passed to the adapter (default: config.MODEL_NAME)
        model_options:   adapter-specific options dict (default: config.MODEL_OPTIONS)
        prompt_template: override the default prompt template (optional)

    Example — banking::

        from translation_service import TranslationService

        service = TranslationService(domain="banking")
        english = service.translate(ocr_text)

    Example — legal::

        service = TranslationService(domain="legal")
        english = service.translate(ocr_text)

    Example — explicit KB path::

        service = TranslationService(kb_path=Path("./my_custom_kb.jsonl"))
    """

    def __init__(
        self,
        domain: str | None = None,
        kb_path: Path | None = None,
        adapter_name: str | None = None,
        model_name: str | None = None,
        model_options: dict | None = None,
        prompt_template: str | None = None,
    ):
        # Resolve domain
        self.domain = domain or _cfg.DEFAULT_DOMAIN

        # KB path: explicit override wins, otherwise derive from domain
        resolved_kb_path = kb_path or _cfg.get_kb_path(self.domain)

        # Fall back to config defaults for model settings
        adapter_name  = adapter_name  or _cfg.MODEL_ADAPTER
        model_name    = model_name    or _cfg.MODEL_NAME
        model_options = model_options or _cfg.MODEL_OPTIONS
        self._prompt  = prompt_template or _cfg.PROMPT_TEMPLATE

        # Load domain knowledge base
        self._kb: list[dict] = load_kb(resolved_kb_path)

        # Instantiate the model adapter
        if adapter_name not in ADAPTERS:
            available = ", ".join(ADAPTERS.keys())
            raise ValueError(
                f"Unknown adapter '{adapter_name}'. Available: {available}"
            )
        adapter_cls: type[ModelAdapter] = ADAPTERS[adapter_name]
        self._adapter: ModelAdapter = adapter_cls(model_name, model_options)

        print(f"[TranslationService] domain={self.domain}, "
              f"kb_entries={len(self._kb)}, "
              f"model={model_name}, adapter={adapter_name}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def translate(self, text: str) -> str:
        """
        Translate a single document string to English.

        Args:
            text: raw OCR source text

        Returns:
            Translated English text as returned by the model.
        """
        matched    = retrieve(text, self._kb)
        term_block = format_terminology_block(matched)
        prompt     = self._prompt.format(
            terminology_block=term_block,
            document=text,
        )
        return self._adapter.translate(prompt)

    def health_check(self) -> bool:
        """Delegate health check to the underlying model adapter."""
        return self._adapter.health_check()

    def health_status(self) -> str:
        """Delegate the non-blocking health status read to the underlying adapter."""
        return self._adapter.health_status()

    async def start_health_monitor(self) -> None:
        """Delegate starting the background health monitor to the underlying adapter."""
        await self._adapter.start_monitoring()

    async def stop_health_monitor(self) -> None:
        """Delegate stopping the background health monitor to the underlying adapter."""
        await self._adapter.stop_monitoring()

    def kb_size(self) -> int:
        """Return the number of terminology entries loaded from the KB."""
        return len(self._kb)

    def kb_matches(self, text: str) -> int:
        """Return the number of KB entries matched for the given text."""
        return len(retrieve(text, self._kb))
