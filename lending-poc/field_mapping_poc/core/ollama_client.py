"""
Thin wrapper around the `ollama` python library.

Keeping this isolated means:
- if Ollama gets swapped for vLLM / a hosted endpoint later, this is
  the only file that needs to change.
- retry / timeout / error-handling logic lives in exactly one place.

Incident notes — read before touching _ping()/health_status(): a chat()
call must NEVER be given a client-side READ timeout. Ollama treats the
client closing that connection as cancellation and aborts an in-progress
cold model load outright. A short-timeout health probe around chat() caused
a load/timeout/abort loop that never let the model finish loading. See the
same issue documented in translation_service's ollama_adapter.py, which
this monitor mirrors. So: never race a health ping's read against a timeout,
and never call it synchronously inside a request handler.

The CONNECT phase is different and must stay bounded — leaving it unbounded
too meant a stopped Ollama hung the probe forever, pinning status at
"initializing". See _ping() and _monitor_loop() below.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx
import ollama

from config import (
    OLLAMA,
    OLLAMA_PING_CONNECT_TIMEOUT_SECONDS,
    OLLAMA_HEALTH_RETRY_SECONDS,
    OLLAMA_HEALTH_MAX_FAST_RETRIES,
    OLLAMA_HEALTH_BACKOFF_SECONDS,
    OLLAMA_HEALTH_RECHECK_SECONDS,
    OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS,
)

logger = logging.getLogger(__name__)


class OllamaClientError(Exception):
    """Raised when the Ollama backend fails after all retries."""


class OllamaClient:
    def __init__(
        self,
        model: str = OLLAMA.model,
        host: str = OLLAMA.host,
        temperature: float = OLLAMA.temperature,
        num_ctx: int = OLLAMA.num_ctx,
        max_retries: int = OLLAMA.max_retries,
    ):
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.max_retries = max_retries
        # Real request path. CONNECT is bounded short (either Ollama is
        # listening or it isn't — a bare timeout=N would apply N to the
        # connect phase too, so a silently-dropped connection would stall for
        # the full circuit-breaker window). READ carries the circuit breaker:
        # long enough to never cut a legitimate cold load, short enough that a
        # wedged Ollama eventually releases _map_lock. See request_timeout in
        # config.py.
        self._client = ollama.Client(
            host=host,
            timeout=httpx.Timeout(
                connect=OLLAMA_PING_CONNECT_TIMEOUT_SECONDS,
                read=OLLAMA.request_timeout,
                write=OLLAMA.request_timeout,
                pool=OLLAMA.request_timeout,
            ),
        )
        # Separate client for health pings: bounded CONNECT, unbounded READ.
        # See _ping() for why the read side must stay unbounded.
        self._ping_client = ollama.Client(
            host=host,
            timeout=httpx.Timeout(
                connect=OLLAMA_PING_CONNECT_TIMEOUT_SECONDS,
                read=None,
                write=None,
                pool=None,
            ),
        )
        # Reachability probe client: short TOTAL timeout is safe here because
        # it only ever hits /api/tags, which lists model files on disk and
        # never triggers a model load — so it carries no abort-a-load risk.
        self._reachability_client = ollama.Client(
            host=host, timeout=OLLAMA_PING_CONNECT_TIMEOUT_SECONDS
        )
        self._status = "initializing"
        self._monitor_task: Optional[asyncio.Task] = None

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """
        Calls the model in JSON mode and returns the raw string response.
        Retries on transient failures with linear backoff (1s, 2s, ...).

        Read timeouts are deliberately NOT retried — see below.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 2):
            try:
                response = self._client.chat(
                    model=self.model,
                    format="json",  # forces the model to emit valid JSON only
                    options={
                        "temperature": self.temperature,
                        "num_ctx": self.num_ctx,
                    },
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response["message"]["content"]
                if not content or not content.strip():
                    raise OllamaClientError("Model returned empty content")
                return content

            except httpx.ReadTimeout as exc:
                # Circuit breaker tripped: we already waited the full read
                # window. Retrying re-waits it from scratch (3 attempts =
                # 3x the window of a held _map_lock), and the timeout just
                # made Ollama abort whatever it was loading, so the retry
                # starts an even slower attempt. Give up now.
                #
                # Note this is ReadTimeout specifically, NOT TimeoutException:
                # ConnectTimeout subclasses that and IS worth retrying, since
                # it fails fast and Ollama may just be mid-restart.
                logger.error(
                    "Ollama read timed out after %ss (attempt %d); not retrying",
                    OLLAMA.request_timeout, attempt,
                )
                raise OllamaClientError(
                    f"Ollama did not respond within {OLLAMA.request_timeout}s"
                ) from exc

            except Exception as exc:  # noqa: BLE001 - retry on anything transient
                last_error = exc
                logger.warning(
                    "Ollama call failed (attempt %d/%d): %s",
                    attempt, self.max_retries + 1, exc,
                )
                if attempt <= self.max_retries:
                    time.sleep(attempt)

        raise OllamaClientError(
            f"Ollama call failed after {self.max_retries + 1} attempts"
        ) from last_error

    def _ping(self) -> None:
        """
        Blocking probe backing the background monitor.

        Timeout split matters here (see module docstring):
        - READ is unbounded. A cold model load can take minutes, and cutting
          the connection mid-load makes Ollama abort the load outright.
        - CONNECT is bounded. Refusing to bound it too was a real bug: with
          Ollama stopped, the probe hung indefinitely, so status never left
          "initializing", the /map fail-fast gate never fired, and requests
          piled up on a doomed call. A connect timeout can't abort a load —
          if the socket is established, the model is by definition loading.

        Uses the same num_ctx as generate_json() so the ping itself can never
        force a reload by asking for a different context size.
        """
        self._ping_client.chat(
            model=self.model,
            messages=[{"role": "user", "content": "ping"}],
            options={"num_ctx": self.num_ctx, "num_predict": 1},
        )

    def _probe_reachable(self) -> None:
        """
        Cheap "is the Ollama server up?" check, independent of model state.
        Hits /api/tags (a disk listing), so it answers fast even while a
        model is cold-loading, and can't abort that load.

        This is what separates "unreachable" from "initializing": the server
        being up but the model not yet answering is precisely "initializing".
        """
        self._reachability_client.list()

    def health_status(self) -> str:
        """
        Instant, non-blocking read for the FastAPI /health route. Never
        calls Ollama itself — reflects whatever the background monitor
        (started via start_monitoring()) last observed.
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
        thread with its READ phase unbounded and never cancelled mid-flight,
        so it can never trigger the abort-on-close incident described in the
        module docstring (only its connect phase is bounded, which is safe —
        see _ping()). Starts with a one-time offset so
        this service's steady-state pings land staggered relative to
        translation_service's own independent monitor, which pings the same
        shared Ollama model on the same cadence — see
        OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS in config.py.
        """
        await asyncio.sleep(OLLAMA_HEALTH_MONITOR_OFFSET_SECONDS)

        consecutive_failures = 0
        while True:
            # Two-phase probe, so each status means exactly one thing and
            # never flaps between them while a probe is in flight:
            #   server down                  -> "unreachable"
            #   server up, model not ready   -> "initializing"
            #   model answered               -> "ok"
            # Getting this wrong is not cosmetic — api.py's /map gate 503s on
            # "unreachable" only, so a status that briefly reads the wrong
            # value either lets doomed requests pile up on _map_lock or
            # rejects cold-load requests that would have succeeded.
            try:
                await asyncio.to_thread(self._probe_reachable)
            except Exception as exc:
                consecutive_failures += 1
                self._status = "unreachable"
                await self._backoff(consecutive_failures, exc)
                continue

            # Server is up. Anything not yet confirmed working is a model
            # that hasn't answered yet — report that honestly rather than
            # holding a stale "unreachable" through a multi-minute cold load
            # (which would make the gate reject requests that would succeed).
            # Guarded so a healthy service never dips out of "ok" mid-recheck.
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
        logger.warning(
            "OllamaClient monitor: %s; retry #%d in %ds",
            exc, consecutive_failures, delay,
        )
        await asyncio.sleep(delay)
