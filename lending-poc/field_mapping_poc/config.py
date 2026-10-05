"""
Central configuration for the Field Mapping POC.

Keep all environment-tunable values here so nothing is hardcoded deep
inside business logic. Override any of these via environment variables
without touching code.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaConfig:
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "gemma4:e4b-it-qat")
    temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.0"))
    # Must match translation_service's num_ctx 
    num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
    request_timeout: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))
    max_retries: int = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))


OLLAMA = OllamaConfig()

# --- Background /health monitor timing ----------------------------------

OLLAMA_PING_CONNECT_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_PING_CONNECT_TIMEOUT_SECONDS", "5"))
OLLAMA_HEALTH_RETRY_SECONDS = float(os.getenv("OLLAMA_HEALTH_RETRY_SECONDS", "5"))
OLLAMA_HEALTH_MAX_FAST_RETRIES = int(os.getenv("OLLAMA_HEALTH_MAX_FAST_RETRIES", "12"))
OLLAMA_HEALTH_BACKOFF_SECONDS = float(os.getenv("OLLAMA_HEALTH_BACKOFF_SECONDS", "120"))
OLLAMA_HEALTH_RECHECK_SECONDS = float(os.getenv("OLLAMA_HEALTH_RECHECK_SECONDS", "30"))

OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS = float(
    os.getenv("OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS", str(OLLAMA_HEALTH_RECHECK_SECONDS / 2))
)

# --- Extra-field flagging convention -----------------------------------

EXTRA_FIELD_VALUE_KEY = "value"
EXTRA_FIELD_SOURCE_KEY = "source"
EXTRA_FIELD_SOURCE_TAG = "llm_added"
SCHEMA_FIELD_SOURCE_TAG = "schema"
