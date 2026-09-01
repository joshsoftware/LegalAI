"""
ollama_adapter.py — ModelAdapter implementation backed by a local Ollama instance.

Prerequisites:
  - Ollama installed and running  (https://ollama.com)
  - Target model pulled:  ollama pull <model_name>

Swapping to a different Ollama model requires only a config.py change (MODEL_NAME).
Swapping to a completely different backend requires a new adapter file; this file
does not need to change.

Incident notes — read before touching health_check()/health_status():
A chat()/generate() call must NEVER be given a client-side READ timeout.
Ollama treats the client closing that connection as cancellation and aborts an
in-progress cold model load outright ("client connection closed before
llama-server finished loading, aborting load"). A short-timeout health probe
around chat() caused a load/timeout/abort loop that never let the model
finish loading. The fix is not to avoid chat() — it's to never race its read
against a timeout and never call it synchronously inside a request handler.

The CONNECT phase is the exception and must stay bounded. It completes before
Ollama receives the request and starts loading, so by the time a load is
underway the connect timeout is already satisfied and disarmed — it can only
fire when no connection was ever established, i.e. when there is no load to
abort. Leaving it unbounded meant a stopped Ollama hung the probe forever and
pinned status at whatever it last was. See _ping() and _monitor_loop() below.
"""

import asyncio

import httpx
import ollama
from ollama import ChatResponse
from .base import ModelAdapter
from ..config import (
    OLLAMA_PING_CONNECT_TIMEOUT_SECONDS,
    OLLAMA_REQUEST_TIMEOUT_SECONDS,
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

        # host=None is deliberate: this adapter takes no host and relies on
        # the ollama library reading OLLAMA_HOST itself, which ollama.Client
        # also does (_parse_host(host or os.getenv(...))) — so None preserves
        # the previous module-level chat() behaviour exactly.
        #
        # Shared by translate() and _ping(), since both talk to the model and
        # want the same policy: short CONNECT, generous READ. See the module
        # docstring for why the connect bound is the safe one, and
        # OLLAMA_REQUEST_TIMEOUT_SECONDS in config.py for how the read ceiling
        # is chosen (far above any normal generation; a last resort only).
        # httpx.Client is thread-safe and both callers run on worker threads.
        #
        # The read bound covers _ping() too. That's intentional: it holds no
        # lock, but an unbounded ping read means a wedged Ollama freezes the
        # monitor loop mid-iteration, so health_status() would sit on a stale
        # value forever instead of eventually reporting the problem.
        self._client = ollama.Client(
            host=None,
            timeout=httpx.Timeout(
                connect=OLLAMA_PING_CONNECT_TIMEOUT_SECONDS,
                read=OLLAMA_REQUEST_TIMEOUT_SECONDS,
                write=OLLAMA_REQUEST_TIMEOUT_SECONDS,
                pool=OLLAMA_REQUEST_TIMEOUT_SECONDS,
            ),
        )
        # Reachability probe: a short TOTAL timeout is safe here because it
        # only ever hits /api/tags, which lists model files on disk and never
        # triggers a load — so nothing can be aborted by closing it.
        self._reachability_client = ollama.Client(
            host=None, timeout=OLLAMA_PING_CONNECT_TIMEOUT_SECONDS
        )

    def translate(self, prompt: str) -> str:
        """
        Send the prompt to Ollama and return the response text.

        Both bounds exist to stop this call holding routes.py's
        _translate_lock indefinitely, which would wedge the endpoint for every
        later caller until the process is restarted:
        - CONNECT is short — a connection that hangs rather than being cleanly
          refused would otherwise block here forever.
        - READ is generous (OLLAMA_REQUEST_TIMEOUT_SECONDS) — a cold load or a
          long document must be waited out, never raced, so this is a
          last-resort ceiling for a wedged Ollama, not a per-request deadline.
          See that constant for the caveat about very long documents.
        """
        response: ChatResponse = self._client.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            options=self.model_options,
        )
        return response["message"]["content"]

    def _ping(self) -> None:
        """
        Blocking probe shared by health_check() (CLI) and the background
        monitor (server). Short connect, generous read — see the module
        docstring and the client construction in __init__.

        Uses the same model_options as translate() (only num_predict is
        overridden) so the ping never causes Ollama to reload the model with
        a different context size than real translate calls use — a mismatch
        that was forcing a full llama-server restart (~250s) on every ping/
        translate interleaving.
        """
        self._client.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": "ping"}],
            options={**self.model_options, "num_predict": 1},
        )

    def _probe_reachable(self) -> None:
        """
        Cheap "is the Ollama server up?" check, independent of model state.
        Hits /api/tags (a disk listing), so it answers fast even while a model
        is cold-loading, and can't abort that load.

        This is what separates "unreachable" from "initializing": the server
        being up but the model not yet answering is precisely "initializing".
        """
        self._reachability_client.list()

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
        Background loop backing health_status(). Runs _ping() on a worker
        thread with its read phase unbounded and never cancelled mid-flight,
        so it can never trigger the abort-on-close incident described in the
        module docstring. Retries quickly at first, then backs off to a slow,
        indefinite retry once a genuine outage looks sustained, and keeps
        re-confirming "ok" so a later outage is eventually reflected too.
        """
        consecutive_failures = 0
        while True:
            # Two-phase probe, so each status means exactly one thing and
            # never flaps between them while a probe is in flight:
            #   server down                  -> "unreachable"
            #   server up, model not ready   -> "initializing"
            #   model answered               -> "ok"
            # A single probe cannot tell the first two apart, which previously
            # made a healthy service dip to "initializing" for the duration of
            # every ping, and made "initializing" during a cold load merely a
            # leftover value rather than an actual finding.
            try:
                await asyncio.to_thread(self._probe_reachable)
            except Exception as exc:
                consecutive_failures += 1
                self._status = "unreachable"
                await self._backoff(consecutive_failures, exc)
                continue

            # Server is up. Anything not yet confirmed working is a model that
            # hasn't answered yet — report that rather than holding a stale
            # "unreachable" through a multi-minute cold load. Guarded so a
            # healthy service never dips out of "ok" mid-recheck.
            if self._status != "ok":
                self._status = "initializing"

            try:
                await asyncio.to_thread(self._ping)
                self._status = "ok"
                consecutive_failures = 0
                await asyncio.sleep(OLLAMA_HEALTH_RECHECK_SECONDS)
            except Exception as exc:
                consecutive_failures += 1
                self._status = "unreachable"
                await self._backoff(consecutive_failures, exc)

    async def _backoff(self, consecutive_failures: int, exc: Exception) -> None:
        """
        Sleep between failed probes: retry quickly at first, then slow down
        once an outage looks sustained, retrying indefinitely so the service
        self-heals without a restart.
        """
        if consecutive_failures <= OLLAMA_HEALTH_MAX_FAST_RETRIES:
            delay = OLLAMA_HEALTH_RETRY_SECONDS
        else:
            delay = OLLAMA_HEALTH_BACKOFF_SECONDS
        print(f"[OllamaAdapter] monitor: {exc}; retry #{consecutive_failures} in {delay}s")
        await asyncio.sleep(delay)
