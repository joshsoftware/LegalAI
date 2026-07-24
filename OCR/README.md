# OCR Text Extraction

A standalone, reusable PDF text-extraction module with a **pluggable OCR engine architecture**. It converts PDF documents into clean, structured, machine-readable output — designed to be plugged into any downstream pipeline (search indexing, LLM ingestion, analytics, etc.) as an independent building block, either as a CLI tool or as an importable Python package.

Ships today with [Surya OCR](https://github.com/datalab-to/surya) as the default (and only) built-in engine, but the OCR backend is fully swappable — see [Pluggable OCR engines](#pluggable-ocr-engines) below.

## Why this exists

Raw OCR output isn't directly usable — it's messy (per-block HTML fragments, layout labels, confidence scores mixed in), and it's usually tightly coupled to one specific OCR library. This project fixes both problems:

- **Humans** get a readable, well-formatted HTML report to review documents visually.
- **Machines / other services** get plain text (simple to embed/search/feed to an LLM) **and** structured JSON (field-mapped, for programmatic consumption — databases, APIs, downstream processing).
- **The OCR backend itself is decoupled** behind a small interface, so swapping Surya for Tesseract, a vLLM-hosted vision model, a cloud OCR API, etc. never requires touching the pipeline, formatter, or CLI — only a new engine adapter.

This makes text extraction a **decoupled, standalone concern**. Any other project can import this package directly (`from extractor import Extractor`) or just read the output files from a known folder, without depending on Surya, vllm/llama.cpp, or any OCR-specific code.

## Scope (v1)

- **Input**: PDFs only, for now. (Images like `.png`/`.jpg` are a future extension — the loader will be written so adding them later is trivial, but v1 only wires up PDFs.)
- **Input location**: defaults to `extraction_input/` (can contain PDFs directly, or PDFs nested inside subfolders), but is **not hardcoded** — the CLI accepts an optional path argument to point at a specific PDF or a different folder instead. See [CLI](#cli) below.
- **Output location**: one consolidated folder, `extraction_output/`, containing three subfolders — one per output format. Each processed PDF produces one file of the same base name in each subfolder.
- **OCR engine**: defaults to Surya, selectable via `--engine` (CLI) or the `engine=` constructor argument (package API). Only `surya` ships today, but the architecture supports adding more without changing any existing code.

## Installation & Setup

These steps are relative to this module's own folder (wherever it lives inside a larger repository) — they don't assume this is the repo root.

### Prerequisites
- Python 3.11+
- macOS/Linux (Surya's inference backend spawns a local `vllm` or `llama.cpp` process)

### 1. Enter this module's folder
```bash
cd path/to/this/module   # e.g. cd services/ocr-extraction
```

### 2. Create and activate a virtual environment (scoped to this module)
```bash
python3.11 -m venv surya-env
source surya-env/bin/activate        # macOS/Linux
# surya-env\Scripts\activate         # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
`requirements.txt` currently contains:
```
surya-ocr
pypdfium2
pillow
```
`surya-ocr` pulls in Surya's inference stack (including its `vllm`/`llama.cpp` backend management) — no separate model download step is required; Surya downloads/spawns its own inference backend automatically on first use.

### 4. Add your PDFs
Drop PDF files (optionally in nested subfolders) into `extraction_input/` inside this module's folder:
```
extraction_input/
├── some_document.pdf
└── nested_folder/
    └── another_document.pdf
```

### 5. Run the extraction
```bash
python main.py
```
This processes every PDF under `extraction_input/` using the default `surya` engine, and writes `.html`, `.txt`, and `.json` outputs to `extraction_output/html/`, `extraction_output/text/`, `extraction_output/json/` respectively.

**First run note:** Surya spawns its inference backend (vllm/llama.cpp) the first time OCR runs — this can take a bit longer on the very first invocation. Subsequent PDFs processed in the same `python main.py` run reuse the same backend instance (see [Use as a package](#use-as-a-package) for why).

### 6. Check the output
```bash
cat extraction_output/text/some_document.txt      # plain text
open extraction_output/html/some_document.html    # human-readable report (macOS)
cat extraction_output/json/some_document.json      # structured JSON
```

### Processing a single file or custom folder (without touching `extraction_input/`)
```bash
python main.py path/to/specific/file.pdf
python main.py path/to/some/other/folder
```

### Using it from another service in the same repo
If another service in this repo wants to call this module directly in-process rather than shelling out to `main.py`, see [Use as a package](#use-as-a-package) below — install this module's `requirements.txt` into that service's environment (or make this module pip-installable/a shared dependency), then `from extractor import Extractor`.

## Project Structure


```
OCR/
├── extractor/                      # Core, importable Python package
│   ├── __init__.py                  # Public API: exports `Extractor` (the only public entry point)
│   ├── models.py                     # Engine-agnostic result model: Block, PageResult dataclasses
│   ├── loader.py                     # PDF -> list of PIL Images (page-by-page rendering)
│   ├── formatter.py                  # Generic PageResult/Block -> plain text / HTML / JSON
│   ├── pipeline.py                   # `Extractor` class: orchestrates load -> OCR -> format -> save
│   └── engines/                      # Pluggable OCR backends
│       ├── __init__.py                # ENGINE_REGISTRY + get_engine() factory
│       ├── base.py                    # BaseOCREngine ABC — the contract every engine implements
│       └── surya_engine.py            # SuryaEngine(BaseOCREngine) - wraps Surya's inference API
├── main.py                          # CLI entry point: `python main.py [path] [--engine NAME]`
├── extraction_input/                 # Default input folder (PDFs, can have nested subfolders)
│   └── ... *.pdf
├── extraction_output/                # Hardcoded output folder (auto-created)
│   ├── html/
│   │   └── <pdf_name>.html
│   ├── text/
│   │   └── <pdf_name>.txt
│   └── json/
│       └── <pdf_name>.json
├── requirements.txt
└── README.md
```

## Pluggable OCR engines

The pipeline never talks to Surya (or any OCR library) directly. It only depends on:

1. **`extractor/engines/base.py` — `BaseOCREngine`**, an abstract class with a single required method:
   ```python
   class BaseOCREngine(ABC):
       @abstractmethod
       def run(self, images: List[PIL.Image]) -> List[PageResult]:
           ...
   ```
2. **`extractor/models.py` — `Block` / `PageResult`**, a small engine-agnostic dataclass contract that every engine must translate its native output into:
   ```python
   @dataclass
   class Block:
       label: str            # "Text", "SectionHeader", "Table", "Picture", ...
       html: str              # recognized content as HTML
       bbox: List[float]      # [x0, y0, x1, y1]
       confidence: float = 1.0
       reading_order: int = 0
       skipped: bool = False  # True for non-OCR'd blocks (e.g. pure images)

   @dataclass
   class PageResult:
       blocks: List[Block]
   ```

`formatter.py` and `pipeline.py` are written entirely against this model — they have zero knowledge of Surya's actual object shapes. All Surya-specific translation logic lives in one place: `extractor/engines/surya_engine.py`.

### Adding a new OCR engine

1. Create `extractor/engines/your_engine.py`:
   ```python
   from .base import BaseOCREngine
   from ..models import Block, PageResult

   class YourEngine(BaseOCREngine):
       def run(self, images):
           # call your OCR backend, then map its output into Block/PageResult
           return [PageResult(blocks=[...]) for image in images]
   ```
2. Register it in `extractor/engines/__init__.py`:
   ```python
   ENGINE_REGISTRY = {
       "surya": SuryaEngine,
       "your_engine": YourEngine,
   }
   ```
3. Done. Use it immediately, with **no other file needing changes**:
   ```bash
   python main.py --engine your_engine
   ```
   ```python
   Extractor(engine="your_engine")
   ```

You can also skip the registry entirely and inject an already-constructed engine instance directly (handy for tests/mocks):
```python
Extractor(engine=YourEngine())
```

## How it works (pipeline)

1. **Discover** — `pipeline.py` recursively walks `extraction_input/` and collects every `.pdf` file (including nested subfolders).
2. **Load** — `loader.py` opens each PDF with `pypdfium2` and renders every page to a `PIL.Image` at a DPI/scale tuned for OCR accuracy. Handles cleanup (`pdf.close()`).
3. **OCR** — the selected engine (`extractor/engines/*.py`) runs all page images for a document through its OCR backend and returns a list of engine-agnostic `PageResult` objects (one per page).
4. **Format** — `formatter.py` converts that generic result into three parallel outputs (see below).
5. **Save** — each PDF's three outputs are written to `extraction_output/html/`, `extraction_output/text/`, `extraction_output/json/` using the PDF's base filename.

## Output formats

### 1. HTML (`extraction_output/html/<name>.html`) — for humans
A styled, page-by-page report (clean typography, tables rendered as real `<table>`, no layout-label clutter). Meant for visual review in a browser, not for parsing.

### 2. Plain text (`extraction_output/text/<name>.txt`) — for machines (simple case)
All block HTML stripped down to plain text, concatenated in reading order, with clear page-break markers. No markup, no metadata — just the text of the document, ready for embedding, search indexing, or feeding into an LLM prompt. This is the "lowest common denominator" format: any consumer can `open(...).read()` and get usable text with zero parsing logic.

### 3. JSON (`extraction_output/json/<name>.json`) — for machines (structured case)

This needs a real field-mapping design, since OCR output is block-oriented (layout blocks with generic labels), not domain-specific fields. Here's how it maps into JSON:

**What every engine gives us, per PDF (via the `Block`/`PageResult` model):**
- A list of pages
- Each page → list of blocks, each block has:
  - `label` (canonicalized layout type: `Text`, `SectionHeader`, `PageHeader`, `Table`, `ListGroup`, `Picture`, ...)
  - `html` (recognized content, as HTML — tables come back as full `<table>`, math as `<math>`)
  - `bbox` (position on the page)
  - `confidence` (0–1, how sure the engine is)
  - `reading_order` (0-indexed position in the page)
  - `skipped` (true for pure visual blocks like `Picture`, not OCR'd)

**How this maps into our JSON schema:**

Rather than inventing arbitrary business fields (which OCR has no way of knowing — it doesn't know what a "case number" or "invoice total" is), the JSON output stays **structurally faithful to what the engine actually detected**, but cleaned up and renamed into a stable, predictable schema. Field mapping:

| Our JSON field | Source (`Block`/`PageResult` field) | Notes |
|---|---|---|
| `document` | PDF filename | top-level identifier |
| `page_count` | number of pages processed | |
| `pages` | list, one entry per page | |
| `pages[i].page_number` | 1-indexed loop counter | |
| `pages[i].blocks` | `page_result.blocks` | filtered: `skipped` blocks excluded |
| `blocks[j].type` | `block.label` | renamed for clarity (`Text`, `Table`, `SectionHeader`, etc.) |
| `blocks[j].order` | `block.reading_order` | preserves reading order for reconstruction |
| `blocks[j].text` | `block.html`, HTML-stripped | plain text version of this block |
| `blocks[j].html` | `block.html` | raw HTML kept too — useful if a table/structure needs to be preserved (e.g. `<table>` markup for a table block) |
| `blocks[j].confidence` | `block.confidence` | lets downstream consumers filter/flag low-confidence blocks |
| `blocks[j].bbox` | `block.bbox` | `[x0, y0, x1, y1]` — useful if a consumer needs position (e.g. highlighting in a viewer) |

This gives downstream consumers **three levels of granularity to choose from**, without us guessing at business-specific fields we can't reliably extract from generic OCR:
- Want just the text? → concatenate `blocks[*].text` in `order`.
- Want to reconstruct tables/structure? → use `blocks[*].html` where `type == "Table"`.
- Want to filter noisy content? → use `confidence` to drop/flag low-confidence blocks.
- Want visual mapping? → use `bbox`.

**Important limitation to be upfront about:** OCR engines detect *layout* (what kind of block something is — text, header, table) but do **not** understand document semantics (they don't know "this text is the case number" or "this table's second column is the verdict"). So the JSON schema above is a **generic, faithful structuring of OCR output** — not a domain-specific extraction (like "case_number", "judge_name", etc.). If field-level business extraction is needed later (e.g. for legal documents — case number, parties, verdict), that would be a **separate downstream step** (e.g. regex/LLM-based extraction running on top of this JSON's `text`/`blocks`), layered on top of this project rather than baked into the OCR step itself.

Example JSON shape:
```json
{
  "document": "S4",
  "page_count": 4,
  "pages": [
    {
      "page_number": 1,
      "blocks": [
        {
          "type": "PageHeader",
          "order": 0,
          "text": "1 न्यायनिर्णय सं.पौ. ख. क्र. ७२२/२०२०",
          "html": "<p>...</p>",
          "confidence": 0.97,
          "bbox": [34.0, 12.0, 560.0, 48.0]
        },
        {
          "type": "Text",
          "order": 1,
          "text": "प्राप्त दिनांक : २७.०७.२०२०...",
          "html": "<p>...</p>",
          "confidence": 0.95,
          "bbox": [34.0, 60.0, 560.0, 140.0]
        }
      ]
    }
  ]
}
```

## Use as a package

`Extractor` is the **single public entry point** of this package — everything (CLI included) goes through it.

```python
from extractor import Extractor

# Pick an engine by name (default is "surya")
extractor = Extractor(engine="surya")

# Process one PDF in-memory (no files written) - great for embedding in another service
result = extractor.process_pdf("extraction_input/some/nested/file.pdf")

result.text        # plain text string
result.json_data    # dict, same shape as the JSON file
result.html         # HTML report string

# Or process a whole folder and write html/text/json outputs to disk
results = extractor.run(input_path="extraction_input/", output_dir="extraction_output/")
```

You can also inject a custom or mocked engine instance directly, instead of a name:
```python
from extractor import Extractor
from my_custom_engine import MyEngine

extractor = Extractor(engine=MyEngine())
```

Since the same `Extractor` object reuses one engine instance across every PDF it processes, any backend server the engine spawns (e.g. Surya's vllm/llama.cpp process) only starts once per `Extractor`, not once per document — construct it once and reuse it for batch runs.

## CLI

```bash
python main.py                                # processes everything under extraction_input/ (default)
python main.py path/to/file.pdf                # processes a single specific PDF
python main.py path/to/folder                  # recursively processes all PDFs in a custom folder
python main.py path/to/folder --engine surya    # explicitly select an OCR engine (default: surya)
```
Recursively finds every `.pdf` under the given path (or `extraction_input/` if no path is given), runs OCR, and writes matching `.html`, `.txt`, `.json` files into `extraction_output/html/`, `extraction_output/text/`, `extraction_output/json/` respectively (same base filename as the source PDF, folder structure flattened by filename — if there's a name collision across nested folders, the relative path will be used to disambiguate).

## Accuracy considerations (multilingual documents)

Since sample documents are in Hindi/Marathi/mixed scripts:
- Render scale defaults to produce ~150–200 DPI equivalent (capped at ~2048px width) for legible text — this is the single biggest accuracy lever per Surya's own docs.
- Room to add preprocessing (deskew/binarize) for scanned/blurry documents later, without changing the public API.
- `confidence` scores are surfaced in JSON specifically so low-quality OCR on non-Latin scripts can be flagged/reviewed rather than silently trusted.
