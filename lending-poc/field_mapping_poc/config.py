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
    num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    request_timeout: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    max_retries: int = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))


OLLAMA = OllamaConfig()

# --- Extra-field flagging convention -----------------------------------
# Fields that ARE part of the caller's target schema are passed through
# as plain values (no wrapper) so existing consumers of the schema shape
# don't need to change.
#
# Fields the model discovers that are NOT part of the schema are kept
# flat, at the same nesting level, but wrapped like:
#   "uanNumber": {"value": "101234567890", "source": "llm_added"}
# so downstream code (e.g. the future Neo4j writer) can easily filter
# them out, route them through review, or promote them into the schema.
EXTRA_FIELD_VALUE_KEY = "value"
EXTRA_FIELD_SOURCE_KEY = "source"
EXTRA_FIELD_SOURCE_TAG = "llm_added"
SCHEMA_FIELD_SOURCE_TAG = "schema"
