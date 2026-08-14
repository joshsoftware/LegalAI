# Translation Service

A structured, model-swappable document translation service built for legal OCR output. Originally powered by Gemma via Ollama, the architecture is designed so the underlying model can be replaced without touching any translation or business logic.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Dependencies](#dependencies)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Running the Service](#running-the-service)
- [Swapping the Model](#swapping-the-model)
- [Adding a New Model Backend](#adding-a-new-model-backend)
- [Extending the Knowledge Base](#extending-the-knowledge-base)
- [Using as a Service (Programmatic API)](#using-as-a-service-programmatic-api)

---

## Overview

The service takes plain-text OCR files as input, enriches the translation prompt with matched legal terminology from a knowledge base (RAG-style), sends the prompt to a language model, and writes the translated output to a target directory.

Key design goals:

- **Model-agnostic** — the LLM sits behind an abstract adapter interface. Swapping Gemma for a different model (a different Ollama model, OpenAI, a local Transformers model, etc.) means adding one small adapter file and changing one config value.
- **Independent service** — the translation logic, KB retrieval, model adapter, and runner are fully separated. Any of them can be imported and reused by other services without pulling in the CLI runner.
- **No side effects on import** — nothing runs at module import time. Everything is instantiated explicitly, so the service can be embedded safely in a larger application.

---

## Project Structure

```
test-traslation/
├── translation_service/        # core package — importable by other services
│   ├── __init__.py
│   ├── config.py               # all settings: paths, domains, model, options
│   ├── translator.py           # TranslationService class — main orchestrator
│   ├── adapters/               # one file per model backend
│   │   ├── __init__.py
│   │   ├── base.py             # abstract ModelAdapter interface
│   │   └── ollama_adapter.py   # Ollama implementation (current default)
│   └── kb/                     # knowledge-base (RAG) layer
│       ├── __init__.py
│       ├── loader.py           # loads the JSONL knowledge base file
│       └── retriever.py        # term matching + prompt block formatting
├── templates/                  # domain knowledge bases
│   ├── banking/
│   │   ├── banking_kb.jsonl    # 50 entries: bank statements, salary slips,
│   │   │                       #   cost sheets, Aadhaar, PAN
│   │   ├── schema.json         # KB entry schema for banking domain
│   │   └── README.md
│   └── legal/
│       ├── court_judgments_kb.jsonl  # legal terminology (court judgments & orders)
│       ├── schema.json
│       └── README.md
├── api/
│   ├── __init__.py
│   ├── models.py               # Pydantic request/response schemas
│   └── routes.py               # FastAPI endpoints
├── api_server.py               # FastAPI app + lifespan (one service per domain)
├── run.py                      # CLI entrypoint — batch-processes a folder of .txt files
├── output/                     # translated files written here (auto-created)
├── requirements.txt
├── Makefile
└── README.md
```

### What each layer does

| Layer | File(s) | Responsibility |
|---|---|---|
| Config | `translation_service/config.py` | Paths, domain registry, KB lookup, model settings |
| Adapter interface | `adapters/base.py` | Abstract class every model backend must implement |
| Ollama adapter | `adapters/ollama_adapter.py` | Calls Ollama's `chat()` with the configured model |
| KB loader | `kb/loader.py` | Reads the JSONL file into a list of dicts |
| KB retriever | `kb/retriever.py` | Substring-matches source text, formats the terminology block |
| Translation service | `translator.py` | Wires KB + adapter; exposes `translate()`, `health_check()` |
| API models | `api/models.py` | Pydantic schemas with `domain` field on all requests |
| API routes | `api/routes.py` | `GET /health`, `POST /translate/text`, `POST /translate/files` |
| CLI runner | `run.py` | Batch `.txt` processing with `--domain` flag |

---

## How It Works

```
Input .txt file (OCR text)
        │
        ▼
  KB Retriever
  (substring match against court_judgments_kb.jsonl)
        │
        ▼
  Terminology block injected into prompt
        │
        ▼
  Model Adapter  ◄──── config: model name + options
  (Ollama / other)
        │
        ▼
  Translated English text
        │
        ▼
  Output .txt file
```

The KB retrieval is a fast substring pre-pass — it scans the source text for Devanagari terms that exist in the knowledge base and injects their semantic/literal/note triplets into the prompt before the model sees the document. This suppresses common mistranslations without requiring any embedding infrastructure.

---

## Dependencies

### System dependencies

| Dependency | Purpose | Install |
|---|---|---|
| Python 3.10+ | Runtime | [python.org](https://python.org) |
| Ollama | Runs the local LLM | [ollama.com](https://ollama.com) |
| Gemma model (or replacement) | The translation model | pulled via Ollama (see below) |

### Python packages

```
ollama          # Ollama Python client
```

The project intentionally keeps the dependency list minimal. The only required package beyond the standard library is `ollama`. If you swap to a different backend (e.g. OpenAI), you add that backend's SDK only in the adapter file.

---

## Installation & Setup

### 1. Clone / navigate to the project

```bash
cd test-traslation
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

### 3. Install Python dependencies

```bash
pip install ollama
```

Or if a `requirements.txt` is present:

```bash
pip install -r requirements.txt
```

### 4. Install Ollama

Download from [https://ollama.com](https://ollama.com) and follow the installer for your OS. Verify it's running:

```bash
ollama --version
```

### 5. Pull the model

```bash
ollama pull gemma4:e4b
```

To use a different model, pull that instead and update the config (see [Swapping the Model](#swapping-the-model)).

### 6. Verify the setup

```bash
ollama run gemma4:e4b "Hello, translate: नमस्ते"
```

You should get an English response. Exit with `/bye`.

---

## Domains

The service supports two translation domains, each with its own knowledge base.

| Domain | KB file | Covers |
|---|---|---|
| `banking` | `templates/banking/banking_kb.jsonl` | Bank statements, salary slips, cost sheets, Aadhaar, PAN |
| `legal` | `templates/legal/court_judgments_kb.jsonl` | Court judgments, orders, legal procedures |

The default domain is `banking` (set in `config.py → DEFAULT_DOMAIN`).

### Switching domain

CLI:
```bash
python run.py --domain banking
python run.py --domain legal
```

API (text endpoint):
```json
{ "text": "...", "domain": "banking" }
```

API (files endpoint):
```
POST /translate/files?domain=legal
```

Programmatic:
```python
service = TranslationService(domain="banking")
service = TranslationService(domain="legal")
```

---

## Configuration

All configuration lives in `translation_service/config.py`. No environment variables or separate `.env` files are required for basic use.

```python
# translation_service/config.py

from pathlib import Path

# --- Paths ---
INPUT_DIR  = Path("/path/to/your/ocr/text/files")   # folder of .txt files to translate
OUTPUT_DIR = Path("./output")                        # translated files written here
KB_PATH    = Path("./legal-template/court_judgments_kb.jsonl")  # knowledge base

# --- Model ---
MODEL_ADAPTER = "ollama"          # which adapter to use: "ollama" | "openai" | etc.
MODEL_NAME    = "gemma4:e4b"      # model identifier passed to the adapter

# --- Model options (adapter-specific) ---
MODEL_OPTIONS = {
    "num_predict": 16384,         # max tokens to generate
    "num_ctx":     32768,         # context window size
}
```

Change `MODEL_NAME` to switch models. Change `MODEL_ADAPTER` to switch backends entirely.

---

## Running the Service

Activate your virtual environment first, then:

```bash
python run.py
```

The runner will:
1. Load the knowledge base from `KB_PATH`
2. Glob all `.txt` files in `INPUT_DIR`
3. For each file: match terminology → build prompt → call model → write translated file to `OUTPUT_DIR`

Progress and match counts are printed to stdout. Output filenames match the input filenames.

### Custom paths at runtime

You can override paths without editing config by passing arguments (if the runner exposes CLI args — see `run.py` for the current interface):

```bash
python run.py --input /path/to/texts --output ./results
```

---

## Swapping the Model

### Same backend (Ollama), different model

Open `translation_service/config.py` and change one line:

```python
# before
MODEL_NAME = "gemma4:e4b"

# after — e.g. Llama 3
MODEL_NAME = "llama3.3:latest"
```

Pull the new model first:

```bash
ollama pull llama3.3:latest
```

That's it. Nothing else changes.

### Different backend entirely

See [Adding a New Model Backend](#adding-a-new-model-backend) below, then update config:

```python
MODEL_ADAPTER = "openai"    # or whatever you named your new adapter
MODEL_NAME    = "gpt-4o"
```

---

## Adding a New Model Backend

All model adapters live in `translation_service/adapters/`. Each one implements the same two-method interface defined in `base.py`:

```python
# translation_service/adapters/base.py

from abc import ABC, abstractmethod

class ModelAdapter(ABC):

    @abstractmethod
    def translate(self, prompt: str) -> str:
        """Send prompt to the model and return the response text."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the model/service is reachable."""
        ...
```

### Example: adding an OpenAI adapter

**Step 1** — install the SDK (in your venv only, not in the core package):

```bash
pip install openai
```

**Step 2** — create `translation_service/adapters/openai_adapter.py`:

```python
from openai import OpenAI
from .base import ModelAdapter

class OpenAIAdapter(ModelAdapter):

    def __init__(self, model: str, options: dict):
        self.model = model
        self.options = options
        self.client = OpenAI()          # reads OPENAI_API_KEY from env

    def translate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.options.get("max_tokens", 16384),
        )
        return response.choices[0].message.content

    def health_check(self) -> bool:
        try:
            self.client.models.retrieve(self.model)
            return True
        except Exception:
            return False
```

**Step 3** — register it in `translation_service/adapters/__init__.py`:

```python
from .ollama_adapter import OllamaAdapter
from .openai_adapter import OpenAIAdapter   # add this

ADAPTERS = {
    "ollama": OllamaAdapter,
    "openai": OpenAIAdapter,                # add this
}
```

**Step 4** — update config:

```python
MODEL_ADAPTER = "openai"
MODEL_NAME    = "gpt-4o"
MODEL_OPTIONS = {"max_tokens": 16384}
```

No other files change.

---

## Extending the Knowledge Base

The knowledge base is at `legal-template/court_judgments_kb.jsonl` — one JSON object per line, following the schema in `legal-template/schema.json`.

To add entries, edit `legal-template/build_kb.py` (the source of truth) and regenerate:

```bash
python legal-template/build_kb.py
```

The retriever in `kb/retriever.py` does a substring match on the `marathi` field of each entry. Adding a new entry is sufficient for it to be picked up — no reindexing or restarting needed.

For embedding-based retrieval (to catch inflected/compound forms the substring pass misses), extend `kb/retriever.py` to add an embedding search step after the substring pass. The `TranslationService` in `translator.py` calls `retriever.retrieve()` and passes back whatever list of entries it returns, so the change is fully contained to the retriever.

---

## FastAPI HTTP Service

The service can be run as an HTTP API using FastAPI. This is useful when the OCR engine or other services need to call translation remotely, or when you want to expose a REST interface.

### Install dependencies

```bash
pip install -r requirements.txt
```

### Start the server

```bash
# development (auto-reload on file changes)
uvicorn api_server:app --reload --port 8001

# production
uvicorn api_server:app --host 0.0.0.0 --port 8001 --workers 1
```

> Keep `--workers 1`. The Ollama model handles one request at a time. For concurrency, run multiple service instances behind a load balancer.

The interactive docs are available at `http://localhost:8001/docs` once the server is running.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Model reachability + current config |
| `POST` | `/translate/text` | Translate a plain-text string (JSON body) |
| `POST` | `/translate/files` | Translate one or more uploaded `.txt` files |

---

#### `GET /health`

```bash
curl http://localhost:8001/health
```

```json
{
  "status": "ok",
  "model": "gemma4:e4b",
  "adapter": "ollama",
  "kb_entries": 100
}
```

---

#### `POST /translate/text`

Accepts a JSON body with a `text` field.

```bash
curl -X POST http://localhost:8001/translate/text \
  -H "Content-Type: application/json" \
  -d '{"text": "न्यायालयाने आरोपीला दोषी ठरवले आणि तीन वर्षांच्या तुरुंगवासाची शिक्षा सुनावली."}'
```

```json
{
  "result": {
    "source": "direct_text",
    "translation": "The court found the accused guilty and sentenced him to three years imprisonment.",
    "kb_matches": 3
  }
}
```

---

#### `POST /translate/files`

Accepts one or more `.txt` file uploads. Returns a result per file. A failure on one file does not abort the others.

```bash
curl -X POST http://localhost:8001/translate/files \
  -F "files=@document_001.txt" \
  -F "files=@document_002.txt"
```

```json
{
  "results": [
    { "source": "document_001.txt", "translation": "The court...", "kb_matches": 4 },
    { "source": "document_002.txt", "translation": "In the matter of...", "kb_matches": 2 }
  ],
  "total": 2,
  "succeeded": 2,
  "failed": 0
}
```

---

### Calling from the OCR service (Phase 2)

Once both services expose HTTP endpoints, the OCR service can call translation directly:

```python
import httpx

with open("ocr_output.txt", "rb") as f:
    response = httpx.post(
        "http://localhost:8001/translate/files",
        files={"files": ("ocr_output.txt", f, "text/plain")},
    )

results = response.json()["results"]
for r in results:
    print(r["source"], "→", r["translation"][:80])
```

---

## Using as a Service (Programmatic API)

The `TranslationService` class can be imported and used directly by other services without going through the CLI runner.

```python
from translation_service.translator import TranslationService
from translation_service.config import KB_PATH, MODEL_ADAPTER, MODEL_NAME, MODEL_OPTIONS

# instantiate once (loads KB, initializes adapter)
service = TranslationService(
    kb_path=KB_PATH,
    adapter_name=MODEL_ADAPTER,
    model_name=MODEL_NAME,
    model_options=MODEL_OPTIONS,
)

# translate a single document string
english_text = service.translate(source_text)

# health check before sending requests
if service.health_check():
    english_text = service.translate(source_text)
```

Because the service has no module-level side effects, multiple instances with different configs (e.g. different models for different document types) can coexist in the same process.

---

## OCR ↔ Translation Communication

The OCR engine and translation service are independent — they communicate through a **shared directory**. No network calls or message brokers are needed at this stage.

```
OCR Engine                              Translation Service
(surya_ocr or similar)                  (this service)

  processes image / PDF
  └── writes .txt files   ──────────►   run.py reads INPUT_DIR/*.txt
      to shared folder                  └── translates each file
                                        └── writes to OUTPUT_DIR/
```

The only contract between the two services is a folder path, set in `config.py → INPUT_DIR`.

### Phase 1 — Manual trigger (now)

Run each service independently. When OCR finishes writing to its output folder, run translation:

```bash
# terminal 1 — OCR engine produces .txt files
python ocr_engine/run.py

# terminal 2 — translation reads those files
python run.py
```

### Phase 1.5 — Pipeline script (chain them)

A thin `pipeline.py` script calls OCR then translation in sequence with no architecture change:

```python
# pipeline.py
import subprocess, sys

subprocess.run([sys.executable, "ocr_engine/run.py"], check=True)
subprocess.run([sys.executable, "run.py"], check=True)
```

Or, if the OCR engine exposes a Python function:

```python
from ocr_engine import run_ocr
from translation_service import TranslationService
from translation_service import config

run_ocr(input_path="./documents", output_path=config.INPUT_DIR)

service = TranslationService(...)
for txt_file in config.INPUT_DIR.glob("*.txt"):
    translated = service.translate(txt_file.read_text(encoding="utf-8"))
    (config.OUTPUT_DIR / txt_file.name).write_text(translated, encoding="utf-8")
```

### Phase 2 — FastAPI HTTP (future)

When you need remote access or multi-user support, each service gets an endpoint and they communicate over HTTP. The translation service structure already supports this — `TranslationService.translate(text)` maps directly to a `POST /translate` route. See the *Using as a Service* section for the wrapper code.

---

## Notes

- The `output/` directory is created automatically if it does not exist.
- The original `main.py` is kept as-is for reference. The new entrypoint is `run.py`.
- The 7 KB entries flagged `needs_sme_review` are included in retrieval but their `semantic_english` should be treated as a strong default, not a guaranteed-correct answer, until reviewed by a bilingual legal professional.
- This service processes `.txt` files (post-OCR). OCR itself (e.g. Surya OCR) is a separate upstream step and is not part of this service.
