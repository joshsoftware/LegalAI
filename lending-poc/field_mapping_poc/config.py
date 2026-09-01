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
    # Must match translation_service's num_ctx (see
    # ../document_processing/translation/translation_service/config.py).
    # Ollama treats a different num_ctx as a different model runtime, so a
    # mismatch here makes it evict and cold-reload the model every time
    # this service and translation take turns calling it (~2min each time
    # on CPU), instead of sharing one resident instance.
    num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
    # READ-phase circuit breaker for a wedged Ollama, NOT a per-request SLA.
    # Bounded from below and above:
    #   - Must exceed a real cold load (~215s measured on CPU). Firing
    #     mid-load makes Ollama abort it, so the next request reloads from
    #     scratch — that cascade was the original /map incident.
    #   - Must not run too far past the gateway's own 300s proxy timeout.
    #     Once that fires nobody is waiting for the answer, but this call
    #     still holds _map_lock, blocking every other /map caller.
    # 600s is ~3x the observed load with ~5min of post-abandonment lock hold.
    # Raise it (env) for slower hosts or larger models, where a legitimate
    # load could otherwise cross it.
    request_timeout: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))
    max_retries: int = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))


OLLAMA = OllamaConfig()

# --- Background /health monitor timing ----------------------------------
# Mirrors translation_service/config.py's OLLAMA_HEALTH_* constants (same
# env var names/defaults — both services describe the same "how hard to
# retry pinging local Ollama" concern for the same shared Ollama instance).
# The monitor probes Ollama on a background task — never inline in a request
# — so these control retry/recheck cadence only, never a request timeout.

# Connect-phase timeout for the health monitor's probes ONLY, never a read
# timeout (see _ping() in core/ollama_client.py: the read must stay unbounded
# so a probe can't abort an in-progress cold model load). Bounds how long a
# probe waits to establish a TCP connection, so a stopped/unroutable Ollama is
# reported "unreachable" promptly instead of the probe hanging indefinitely
# and leaving status stuck on "initializing".
OLLAMA_PING_CONNECT_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_PING_CONNECT_TIMEOUT_SECONDS", "5"))
OLLAMA_HEALTH_RETRY_SECONDS = float(os.getenv("OLLAMA_HEALTH_RETRY_SECONDS", "5"))
OLLAMA_HEALTH_MAX_FAST_RETRIES = int(os.getenv("OLLAMA_HEALTH_MAX_FAST_RETRIES", "12"))
OLLAMA_HEALTH_BACKOFF_SECONDS = float(os.getenv("OLLAMA_HEALTH_BACKOFF_SECONDS", "120"))
OLLAMA_HEALTH_RECHECK_SECONDS = float(os.getenv("OLLAMA_HEALTH_RECHECK_SECONDS", "30"))
# translation's monitor also pings on OLLAMA_HEALTH_RECHECK_SECONDS; this
# one-time startup delay staggers this service's steady-state pings to land
# opposite-phase to translation's (~15s/45s vs translation's ~0s/30s) so the
# two independent monitors don't both hit the shared Ollama model at once.
OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS = float(
    os.getenv("OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS", str(OLLAMA_HEALTH_RECHECK_SECONDS / 2))
)

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
