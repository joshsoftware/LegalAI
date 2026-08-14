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

        Used by run.py before starting a batch and by the future /health endpoint.
        Should not raise — catch exceptions internally and return False.
        """
        ...
