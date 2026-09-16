"""
base.py — abstract interface every model adapter must implement.

To add a new backend:
  1. Create a new file in this directory (e.g. openai_adapter.py)
  2. Subclass ModelAdapter and implement translate() and health_check()
  3. Register it in adapters/__init__.py
  4. Set MODEL_ADAPTER in config.py to your new key
"""

from abc import ABC, abstractmethod


class ModelAdapter(ABC):
    """
    Common interface for all model backends.

    Every adapter receives the fully-rendered prompt string and returns
    the model's plain-text response. Adapters are responsible for their
    own SDK initialisation, retry logic, and error handling.
    """

    @abstractmethod
    def translate(self, prompt: str) -> str:
        """
        Send prompt to the model and return the response text.

        Args:
            prompt: fully-rendered translation prompt (text + terminology block)

        Returns:
            The model's response as a plain string.

        Raises:
            RuntimeError: if the model call fails after retries.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """
        Return True if the model / backend service is reachable.

        Blocking — used by run.py before starting a batch. Should not raise —
        catch exceptions internally and return False.
        """
        ...

    def health_status(self) -> str:
        """
        Return one of "ok", "initializing", "unreachable" for the FastAPI
        /health endpoint. Non-blocking by contract — should be an instant read
        of previously-observed state, not a fresh call to the backend.

        Default implementation falls back to a blocking health_check() call,
        for adapters that don't track finer-grained state. Override alongside
        start_monitoring()/stop_monitoring() to report real-time state instead.
        """
        return "ok" if self.health_check() else "unreachable"

    async def start_monitoring(self) -> None:
        """
        Optional hook: begin any background readiness tracking backing
        health_status(). Default is a no-op — adapters that don't override
        this just rely on health_status()'s default blocking fallback.
        """
        return

    async def stop_monitoring(self) -> None:
        """Optional hook: stop background tracking started by start_monitoring()."""
        return
