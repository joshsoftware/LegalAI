"""
config.py — single source of truth for all service settings.

To swap the model : change MODEL_NAME (same backend)
                    or MODEL_ADAPTER + MODEL_NAME (new backend).
To change I/O dirs: change INPUT_DIR / OUTPUT_DIR.
To change domain  : change DEFAULT_DOMAIN to "legal" or "banking".
Nothing outside this file needs to change for those operations.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Directory containing .txt files produced by the OCR engine.
# OCR service writes here → translation service reads from here.
INPUT_DIR = Path("/Users/josh/Desktop/Josh/inovation_lab/surya_ocr_test/extraction_output/text")

# Directory where translated .txt files are written (created automatically).
OUTPUT_DIR = Path("./output")

# Root folder for all domain knowledge bases.
TEMPLATES_DIR = Path("./templates")

# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------

# Supported domains — each must have a matching subfolder under TEMPLATES_DIR.
SUPPORTED_DOMAINS = ["legal", "banking"]

# Default domain used by CLI (run.py) and API when none is specified.
DEFAULT_DOMAIN = "banking"

# KB filename is the same convention in every domain folder.
KB_FILENAME = {
    "legal":   "court_judgments_kb.jsonl",
    "banking": "banking_kb.jsonl",
}


def get_kb_path(domain: str) -> Path:
    """
    Return the Path to the knowledge base file for the given domain.

    Args:
        domain: one of SUPPORTED_DOMAINS ("legal" or "banking")

    Raises:
        ValueError: if the domain is not in SUPPORTED_DOMAINS
    """
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"Unknown domain '{domain}'. Supported: {SUPPORTED_DOMAINS}"
        )
    return TEMPLATES_DIR / domain / KB_FILENAME[domain]


# ---------------------------------------------------------------------------
# Model adapter
# ---------------------------------------------------------------------------

# Which backend to use. Must match a key registered in adapters/__init__.py.
# Supported now: "ollama"
MODEL_ADAPTER = "ollama"

# Model identifier passed to the chosen adapter.
MODEL_NAME = os.getenv("OLLAMA_MODEL", "gemma4:e4b-it-qat")

# Background /health monitor timing (see OllamaAdapter._monitor_loop). The
# monitor pings Ollama with a real chat() call, untimed, on a background task
# — never inline in a request — so these control retry/recheck cadence only,
# never a request timeout.
#
# Fast retry interval while consecutive failures are within the limit below.
OLLAMA_HEALTH_RETRY_SECONDS = float(os.getenv("OLLAMA_HEALTH_RETRY_SECONDS", "5"))
# How many consecutive failures before backing off to the slower interval.
OLLAMA_HEALTH_MAX_FAST_RETRIES = int(os.getenv("OLLAMA_HEALTH_MAX_FAST_RETRIES", "12"))
# Slow retry interval once the fast-retry budget is exhausted — keeps trying
# forever, just less aggressively, so the service self-heals without a restart.
OLLAMA_HEALTH_BACKOFF_SECONDS = float(os.getenv("OLLAMA_HEALTH_BACKOFF_SECONDS", "120"))
# Reconfirmation interval once status is "ok", so a later Ollama outage is
# eventually reflected again instead of leaving /health stuck on stale "ok".
OLLAMA_HEALTH_RECHECK_SECONDS = float(os.getenv("OLLAMA_HEALTH_RECHECK_SECONDS", "30"))

# ---------------------------------------------------------------------------
# Model options  (adapter-specific — passed through as-is)
# ---------------------------------------------------------------------------

MODEL_OPTIONS: dict = {
    # Maximum tokens the model will generate per document.
    "num_predict": 16384,
    # Context window: must fit prompt + terminology block + full document.
    "num_ctx": 32768,
}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
Detect the source language and translate the following OCR document into clear English.

Rules:
- Translate the source text into English strictly based on the provided source text. \
Do not infer, add, omit, summarize, or rewrite any information unless it is explicitly \
present in the source. Preserve all words, fields, labels, numbers, names, dates, \
abbreviations, and document structure as accurately as possible. If a field is empty, \
keep it empty and do not map it to nearby or adjacent text. Translate financial/legal \
terms, abbreviations, and domain-specific terminology using the approved glossary only. \
If a term is unclear or not available in the glossary, preserve the original term \
and flag it for review instead of guessing its meaning.
- Return only the English translation.
- Preserve headings, paragraphs, dates, names, numbers, and lists.
- Correct OCR mistakes only when the intended wording is obvious.
- Do not summarize, omit, or add information.
{terminology_block}
Document:
{document}
"""
