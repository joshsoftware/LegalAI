"""OCR engine registry.

Adding a new engine is a two-step process:
    1. Implement it in a new module here (subclassing `BaseOCREngine`).
    2. Add one line to `ENGINE_REGISTRY` below.

Nothing else in the codebase needs to change - `pipeline.py` only ever
resolves engines through `get_engine()`.
"""

from __future__ import annotations

from typing import Dict, Type, Union

from .base import BaseOCREngine
from .surya_engine import SuryaEngine

ENGINE_REGISTRY: Dict[str, Type[BaseOCREngine]] = {
    "surya": SuryaEngine,
}


def get_engine(engine: Union[str, BaseOCREngine] = "surya") -> BaseOCREngine:
    """Resolve an engine name (or an already-instantiated engine) into a
    ready-to-use `BaseOCREngine` instance.

    Args:
        engine: either a registered engine name (e.g. "surya"), or an
            already-constructed `BaseOCREngine` instance (passed through
            unchanged, so callers can inject a custom/mocked engine).

    Returns:
        A `BaseOCREngine` instance.
    """
    if isinstance(engine, BaseOCREngine):
        return engine

    if isinstance(engine, str):
        try:
            engine_cls = ENGINE_REGISTRY[engine]
        except KeyError as exc:
            available = ", ".join(sorted(ENGINE_REGISTRY))
            raise ValueError(
                f"Unknown OCR engine '{engine}'. Available engines: {available}"
            ) from exc
        return engine_cls()

    raise TypeError(
        "engine must be a registered engine name (str) or a BaseOCREngine "
        f"instance, got {type(engine)!r}"
    )


__all__ = ["BaseOCREngine", "ENGINE_REGISTRY", "get_engine"]
