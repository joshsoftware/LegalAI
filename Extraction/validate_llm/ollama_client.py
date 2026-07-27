"""
Extraction/validate_llm/ollama_client.py
Thin client for a local Ollama model, used as the LLM-review step for
field validation. Model/URL come from shared/config.py (VALIDATION_MODEL,
OLLAMA_URL) — swapping models is a .env change, not a code change.
"""
import json
import logging
import os
import re

import requests
from tenacity import retry, wait_exponential, stop_after_attempt, before_sleep_log, retry_if_exception_type

from shared.config import OLLAMA_URL, VALIDATION_MODEL

logger = logging.getLogger('pipeline')

GENERATE_URL = f"{OLLAMA_URL}/api/generate"

_JSON_OBJECT_RE = re.compile(r'\{.*\}', re.DOTALL)


OLLAMA_TIMEOUT_SECONDS = int(os.environ.get('OLLAMA_TIMEOUT_SECONDS', '300'))


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _call_ollama(prompt: str) -> str:
    logger.info(f"[validate_llm] calling Ollama model={VALIDATION_MODEL!r} url={GENERATE_URL}")
    try:
        resp = requests.post(
            GENERATE_URL,
            json={
                'model': VALIDATION_MODEL,
                'prompt': prompt,
                'stream': False,
                'think': False,
                'options': {'temperature': 0, 'seed': 42},
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        logger.warning(
            f"[validate_llm] Ollama HTTP error: status={resp.status_code} "
            f"body={resp.text[:500]!r}"
        )
        raise
    except requests.exceptions.RequestException as e:
        logger.warning(f"[validate_llm] Ollama connection error: {e!r}")
        raise
    text = resp.json().get('response', '')
    logger.info(f"[validate_llm] Ollama call succeeded model={VALIDATION_MODEL!r}")
    logger.info(f"[validate_llm] Ollama raw response:\n{text}")
    return text


def ask_valid(prompt: str) -> dict | None:
    """
    Send a prompt to the validation model, expecting a JSON object
    {"valid": bool, "reason": str} somewhere in the response.
    Returns the parsed dict, or None if the call/parse failed
    (caller should treat None as "skip — leave field as-is").
    """
    try:
        raw = _call_ollama(prompt)
    except Exception as e:
        logger.warning(f"[validate_llm] Ollama call failed: {e}")
        return None

    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        logger.warning(f"[validate_llm] Ollama returned no JSON object: {raw!r}")
        return None

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning(f"[validate_llm] Ollama returned malformed JSON: {raw!r}")
        return None

    if 'valid' not in parsed:
        logger.warning(f"[validate_llm] Ollama JSON missing 'valid' key: {parsed!r}")
        return None

    return parsed


def ask_json(prompt: str) -> dict | None:
    """
    Send a prompt to the validation model, expecting a single JSON object
    anywhere in the response (fenced or not). Returns the parsed dict, or
    None if the call/parse failed (caller should treat None as "validator
    unavailable — skip").
    """
    try:
        raw = _call_ollama(prompt)
    except Exception as e:
        logger.warning(f"[validate_llm] Ollama call failed: {e}")
        return None

    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        logger.warning(f"[validate_llm] Ollama returned no JSON object: {raw!r}")
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning(f"[validate_llm] Ollama returned malformed JSON: {raw!r}")
        return None


def ask_lines(prompt: str) -> list[str] | None:
    """
    Send a prompt to the validation model, expecting a plain-text
    response of one finding per line (or the literal string NONE).
    Returns the list of non-empty lines, or None if the call failed
    (caller should treat None as "validator unavailable — skip").
    """
    try:
        raw = _call_ollama(prompt)
    except Exception as e:
        logger.warning(f"[validate_llm] Ollama call failed: {e}")
        return None

    return [line for line in raw.splitlines() if line.strip()]
