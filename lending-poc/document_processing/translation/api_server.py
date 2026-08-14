"""
api_server.py — creates and configures the FastAPI application.

One TranslationService instance is created per domain at startup and stored
in app.state.services (a dict keyed by domain name). All routes share these
pre-loaded instances — KB is read once, not per request.

Running
-------
    make api                              # dev, auto-reload, :8001
    uvicorn api_server:app --port 8001    # manual
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from translation_service import TranslationService
from translation_service.config import SUPPORTED_DOMAINS, MODEL_NAME, MODEL_ADAPTER, MODEL_OPTIONS
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load one TranslationService per domain and share across all requests."""
    print("[startup] Loading TranslationService for all domains…")
    app.state.services: dict[str, TranslationService] = {}

    for domain in SUPPORTED_DOMAINS:
        app.state.services[domain] = TranslationService(
            domain=domain,
            model_name=MODEL_NAME,
            model_options=MODEL_OPTIONS,
        )

    print(f"[startup] Ready — model={MODEL_NAME}, adapter={MODEL_ADAPTER}, "
          f"domains={SUPPORTED_DOMAINS}")
    yield
    print("[shutdown] Translation service stopped.")


app = FastAPI(
    title="Translation Service",
    description=(
        "Model-swappable document translation service for Marathi banking and legal documents. "
        "Accepts plain text or uploaded .txt files and returns English translations. "
        "Supports domains: banking (bank statements, salary slips, cost sheets, Aadhaar, PAN) "
        "and legal (court judgments and orders)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
