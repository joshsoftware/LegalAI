"""
adapters/__init__.py — registry of all available model backends.

To register a new adapter:
  1. Create your adapter file in this directory (subclass ModelAdapter)
  2. Import it here and add it to the ADAPTERS dict with a string key
  3. Set MODEL_ADAPTER in config.py to that key
"""

from .ollama_adapter import OllamaAdapter

# Maps the MODEL_ADAPTER config string to the adapter class.
# TranslationService looks up and instantiates the adapter from this dict.
ADAPTERS: dict = {
    "ollama": OllamaAdapter,
    # "openai": OpenAIAdapter,   ← add future adapters here
}

__all__ = ["ADAPTERS"]
