"""
ollama_adapter.py — ModelAdapter implementation backed by a local Ollama instance.

Prerequisites:
  - Ollama installed and running  (https://ollama.com)
  - Target model pulled:  ollama pull <model_name>

Swapping to a different Ollama model requires only a config.py change (MODEL_NAME).
Swapping to a completely different backend requires a new adapter file; this file
does not need to change.
"""

from ollama import chat, ChatResponse
from .base import ModelAdapter


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

    def translate(self, prompt: str) -> str:
        """Send the prompt to Ollama and return the response text."""
        response: ChatResponse = chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            options=self.model_options,
        )
        return response["message"]["content"]

    def health_check(self) -> bool:
        """
        Verify Ollama is running and the configured model is available.
        Sends a minimal prompt to avoid false positives from API-only checks.
        """
        try:
            response: ChatResponse = chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "ping"}],
                options={"num_predict": 1},
            )
            return bool(response["message"]["content"] is not None)
        except Exception as exc:
            print(f"[OllamaAdapter] health_check failed: {exc}")
            return False
