"""
api/models.py — Pydantic request / response schemas for the translation API.
"""

from typing import Literal
from pydantic import BaseModel, Field

from translation_service.config import SUPPORTED_DOMAINS, DEFAULT_DOMAIN

# Build the Literal type dynamically from config so adding a new domain
# in config.py automatically updates the API validation too.
DomainLiteral = Literal["legal", "banking"]

HealthStatus = Literal["ok", "initializing", "unreachable"]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TextTranslateRequest(BaseModel):
    """Body for POST /translate/text — translate a single plain-text string."""

    text: str = Field(
        ...,
        min_length=1,
        description="Raw OCR or plain text to translate into English.",
        examples=["बँकेने कर्जाची रक्कम मंजूर केली आणि खात्यात जमा केली."],
    )
    domain: DomainLiteral = Field(
        default=DEFAULT_DOMAIN,
        description=f"Translation domain — which KB to use. One of: {SUPPORTED_DOMAINS}.",
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TranslationResult(BaseModel):
    """Translation result for a single input (text or file)."""

    source: str = Field(description="Origin label — 'direct_text' or the uploaded filename.")
    domain: str = Field(description="Domain used for this translation.")
    translation: str = Field(description="Translated English text.")
    kb_matches: int = Field(description="Number of terminology KB entries matched.")


class TextTranslateResponse(BaseModel):
    """Response for POST /translate/text."""

    result: TranslationResult


class FilesTranslateResponse(BaseModel):
    """Response for POST /translate/files — one result per uploaded file."""

    results: list[TranslationResult]
    total: int = Field(description="Total number of files submitted.")
    succeeded: int = Field(description="Files that translated without error.")
    failed: int = Field(description="Files that raised an error during translation.")


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: HealthStatus = Field(
        description=(
            "'unreachable' if Ollama isn't responding, 'initializing' if it's "
            "reachable but the model hasn't responded yet (e.g. cold-loading), "
            "'ok' if the model is loaded and responding."
        )
    )
    detail: str = Field(description="Human-readable explanation of `status`.")
    model: str = Field(description="Model name currently configured.")
    adapter: str = Field(description="Adapter/backend currently configured.")
    domains: list[str] = Field(description="Supported translation domains.")
    kb_entries: dict[str, int] = Field(description="Number of KB entries loaded per domain.")
