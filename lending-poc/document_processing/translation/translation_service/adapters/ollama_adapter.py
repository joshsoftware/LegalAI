"""
ollama_adapter.py — ModelAdapter implementation backed by a local Ollama instance.

Prerequisites:
  - Ollama installed and running  (https://ollama.com)
  - Target model pulled:  ollama pull <model_name>

Swapping to a different Ollama model requires only a config.py change (MODEL_NAME).
Swapping to a completely different backend requires a new adapter file; this file
does not need to change.

Incident notes — read before touching health_check()/health_status():
A chat()/generate() call must NEVER be given a client-side timeout. Ollama
treats the client closing that connection as cancellation and aborts an
in-progress cold model load outright ("client connection closed before
llama-server finished loading, aborting load"). A short-timeout health probe
around chat() caused a load/timeout/abort loop that never let the model
finish loading. The fix is not to avoid chat() — it's to never race it against
a timeout and never call it synchronously inside a request handler. See
_ping() and _monitor_loop() below.
"""

import asyncio

from ollama import chat, ChatResponse
from .base import ModelAdapter
from ..config import (
    OLLAMA_HEALTH_RETRY_SECONDS,
    OLLAMA_HEALTH_MAX_FAST_RETRIES,
    OLLAMA_HEALTH_BACKOFF_SECONDS,
    OLLAMA_HEALTH_RECHECK_SECONDS,
)


class OllamaAdapter(ModelAdapter):
    """
    Calls Ollama's local REST API via the official Python client.

    Args:
        model_name:   Ollama model tag, e.g. "gemma4:e4b" or "llama3.3:latest"
        model_options: Dict of Ollama generate options (num_predict, num_ctx, …)
    """

    def __init__(self, model_name: str, model_options: dict):
        self.model_name = model_name
        self.model_options = model_options
        self._status = "initializing"
        self._monitor_task: asyncio.Task | None = None

    def translate(self, prompt: str) -> str:
        """Send the prompt to Ollama and return the response text."""
        response: ChatResponse = chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            options=self.model_options,
        )
        return response["message"]["content"]

    def _ping(self) -> None:
        """
        Blocking probe shared by health_check() (CLI) and the background
        monitor (server). Deliberately untimed — see module docstring.
        """
        chat(
            model=self.model_name,
            messages=[{"role": "user", "content": "ping"}],
            options={"num_predict": 1},
        )

    def health_check(self) -> bool:
        """
        Blocking reachability check for the CLI (run.py). Waits out a cold
        load rather than racing it — appropriate for a one-shot batch script.
        """
        try:
            self._ping()
            return True
        except Exception as exc:
            print(f"[OllamaAdapter] health_check failed: {exc}")
            return False

    def health_status(self) -> str:
        """
        Instant, non-blocking read for the FastAPI /health route. Never calls
        Ollama itself — reflects whatever the background monitor last observed.
        See start_monitoring().
        """
        return self._status

    async def start_monitoring(self) -> None:
        """Begin the background readiness monitor backing health_status()."""
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self) -> None:
        """Stop the background monitor started by start_monitoring()."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

    async def _monitor_loop(self) -> None:
        """
        Background loop backing health_status(). Runs _ping() to completion on
        a worker thread — never given a timeout, never cancelled mid-flight —
        so it can never trigger the abort-on-close incident described in the
        module docstring. Retries quickly at first, then backs off to a slow,
        indefinite retry once a genuine outage looks sustained, and keeps
        re-confirming "ok" so a later outage is eventually reflected too.
        """
        consecutive_failures = 0
        while True:
            self._status = "initializing"
            try:
                await asyncio.to_thread(self._ping)
                self._status = "ok"
                consecutive_failures = 0
                await asyncio.sleep(OLLAMA_HEALTH_RECHECK_SECONDS)
            except Exception as exc:
                consecutive_failures += 1
                self._status = "unreachable"
                if consecutive_failures <= OLLAMA_HEALTH_MAX_FAST_RETRIES:
                    delay = OLLAMA_HEALTH_RETRY_SECONDS
                else:
                    delay = OLLAMA_HEALTH_BACKOFF_SECONDS
                print(f"[OllamaAdapter] monitor: {exc}; retry #{consecutive_failures} in {delay}s")
                await asyncio.sleep(delay)
