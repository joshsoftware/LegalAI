# OCR Text Extraction

A comprehensive document processing system with **pluggable OCR engine architecture**. It extracts text from PDF, PNG, and JPEG files, converting them into clean, structured, machine-readable output. Designed to be used either as a CLI tool, importable Python package, or REST API service.

Ships with [Surya OCR](https://github.com/datalab-to/surya) as the default engine, with full support for pluggable backends.

## Features

- **Multiple Input Formats**: PDF (multi-page), PNG, JPEG (single page)
- **Multiple Interfaces**: CLI tool, Python package, REST API
- **Pluggable OCR Engines**: Swappable backend architecture
- **Multiple Output Formats**: Plain text, HTML, structured JSON
- **Production Ready**: FastAPI web service with proper error handling
- **Easy Development**: Makefile with common development commands

## Why This Exists

Raw OCR output isn't directly usable — it's messy and tightly coupled to specific OCR libraries. This project solves both problems:

- **Humans** get readable, well-formatted HTML reports to review documents visually
- **Machines** get clean plain text (for embedding/search/LLM ingestion) and structured JSON (for programmatic consumption)
- **The OCR backend is decoupled** behind a clean interface, making it easy to swap engines without changing pipeline code
- **Multiple access methods** support different use cases: CLI for batch processing, API for web services, package for integration

## Quick Start

### Using the Makefile (Recommended)

```bash
# Complete service setup and startup (first time users)
make start-service

# Individual commands
make setup                            # Set up the project (creates virtual environment and installs dependencies)
make cli                              # Process documents with CLI
make cli-file FILE=path/to/doc.pdf    # Process specific file
make api                              # Start API server
make status                           # Check project status
make help                             # Get help
```

### Manual Setup

```bash
# Create virtual environment
python3.11 -m venv surya-env
source surya-env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run CLI
python main.py

# Start API server
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## Usage

### 1. Command Line Interface

```bash
# Process all documents in default input folder
python main.py

# Process specific file
python main.py path/to/document.pdf
python main.py path/to/image.png

# Process custom folder
python main.py path/to/folder

# Select OCR engine
python main.py --engine surya
```

**Supported formats**: PDF, PNG, JPEG

### 2. REST API

Start the API server:
```bash
make api-dev
# or
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

#### API Endpoints

- **POST /extract** - Upload and process documents
- **GET /health** - Health check
- **GET /** - API information
- **GET /docs** - Interactive API documentation (Swagger UI)

#### Example API Usage

```bash
# Upload a document for processing
curl -X POST "http://localhost:8000/extract" \
  -F "file=@document.pdf"

# Check API health
curl http://localhost:8000/health

# View interactive docs
open http://localhost:8000/docs
```

#### API Response Format

```json
{
  "filename": "document.pdf",
  "file_type": ".pdf",
  "pages_processed": 3,
  "extraction": {
    "text": "Plain text content...",
    "html": "<html>Formatted content...</html>",
    "structured_data": {
      "document": "document",
      "page_count": 3,
      "pages": [...]
    }
  },
  "metadata": {
    "document_name": "document",
    "processing_engine": "surya"
  }
}
```

### 3. Python Package

```python
from extractor import Extractor

# Create extractor instance
extractor = Extractor(engine="surya")

# Process single document
result = extractor.process_document("path/to/document.pdf")
print(result.text)        # Plain text
print(result.html)        # HTML formatted
print(result.json_data)   # Structured JSON

# Process folder and save outputs
results = extractor.run(
    input_path="extraction_input/",
    output_dir="extraction_output/"
)
```

## Project Structure

```
surya_ocr_test/
├── extractor/                      # Core Python package
│   ├── __init__.py                 # Public API exports
│   ├── models.py                   # Engine-agnostic data models
│   ├── loader.py                   # Document loading (PDF/PNG/JPEG)
│   ├── formatter.py                # Output formatting (text/HTML/JSON)
│   ├── pipeline.py                 # Main Extractor class
│   └── engines/                    # Pluggable OCR backends
│       ├── __init__.py             # Engine registry
│       ├── base.py                 # BaseOCREngine interface
│       └── surya_engine.py         # Surya OCR implementation
├── api.py                          # FastAPI web service
├── main.py                         # CLI entry point
├── Makefile                        # Development commands
├── requirements.txt                # Dependencies
├── extraction_input/               # Default input folder
├── extraction_output/              # Default output folder
│   ├── html/                       # HTML reports
│   ├── text/                       # Plain text files
│   └── json/                       # Structured JSON data
└── README.md
```

## Development Commands

The Makefile provides convenient commands for development:

```bash
make help              # Show all available commands
make start-service     # Complete setup and start API (one-command solution)
make setup             # Set up development environment
make install           # Update dependencies
make clean             # Clean temporary files

make cli               # Run CLI on default folder
make cli-file FILE=path/to/doc.pdf  # Process specific file

make api               # Start API server
make status            # Show project status
```

## Installation & Setup

### Prerequisites
- Python 3.11+
- macOS/Linux (Surya requires local inference backend)

### Dependencies

The project includes both core OCR dependencies and API dependencies:

```txt
# Core OCR dependencies
surya-ocr
pypdfium2
pillow

# API dependencies
fastapi
python-multipart
uvicorn[standard]
```

### First-time Setup

1. **Clone and enter the project directory**
2. **Set up environment**: `make setup`
3. **Add documents** to `extraction_input/` folder
4. **Run extraction**: `make cli` or `make api-dev`

**Note**: First run downloads Surya models and starts inference backend, which may take longer initially.

## Output Formats

### 1. HTML (`extraction_output/html/`) — Human-readable
Styled, page-by-page reports with clean typography. Tables rendered as proper `<table>` elements, suitable for browser viewing and visual document review.

### 2. Plain Text (`extraction_output/text/`) — Machine-friendly
Clean text with layout stripped, concatenated in reading order with page breaks. Ready for embedding, search indexing, or LLM consumption.

### 3. Structured JSON (`extraction_output/json/`) — Programmatic
Detailed structured data preserving:
- Document metadata and page count
- Per-page block information (text, tables, headers)
- Confidence scores and bounding boxes
- Reading order and block types
- Both plain text and HTML versions of each block

Example JSON structure:
```json
{
  "document": "filename",
  "page_count": 2,
  "pages": [
    {
      "page_number": 1,
      "blocks": [
        {
          "type": "Text",
          "order": 0,
          "text": "Plain text content",
          "html": "<p>HTML content</p>",
          "confidence": 0.95,
          "bbox": [x0, y0, x1, y1]
        }
      ]
    }
  ]
}
```

## Pluggable OCR Engines

The system uses a clean engine abstraction that makes swapping OCR backends easy:

### Engine Interface

```python
class BaseOCREngine(ABC):
    @abstractmethod
    def run(self, images: List[PIL.Image]) -> List[PageResult]:
        pass
```

### Adding New Engines

1. **Create engine class** in `extractor/engines/your_engine.py`:
```python
from .base import BaseOCREngine
from ..models import Block, PageResult

class YourEngine(BaseOCREngine):
    def run(self, images):
        # Process images with your OCR backend
        # Return PageResult objects with Block data
        return [PageResult(blocks=[...]) for image in images]
```

2. **Register engine** in `extractor/engines/__init__.py`:
```python
ENGINE_REGISTRY = {
    "surya": SuryaEngine,
    "your_engine": YourEngine,
}
```

3. **Use immediately**:
```bash
python main.py --engine your_engine
```

### Engine Data Model

All engines must translate their output into standardized `Block` and `PageResult` objects:

```python
@dataclass
class Block:
    label: str            # "Text", "Table", "SectionHeader", etc.
    html: str             # Content as HTML
    bbox: List[float]     # [x0, y0, x1, y1] position
    confidence: float     # 0-1 confidence score
    reading_order: int    # Order within page
    skipped: bool         # True for non-text blocks (images)
```

This ensures the pipeline, formatters, and API work consistently regardless of the underlying OCR engine.

## API Documentation

### Interactive Documentation
When the API server is running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Rate Limits and File Limits
- **Max file size**: 50MB
- **Supported formats**: PDF, PNG, JPEG
- **Concurrent processing**: Single-threaded (suitable for most use cases)

### Error Handling
The API provides detailed error responses for:
- Unsupported file formats
- File size limits
- Processing errors
- Invalid requests

## Accuracy Considerations

### Multilingual Support
Optimized for multilingual documents including Indic scripts:
- **Render scale**: Tuned for ~150-200 DPI equivalent
- **Image preprocessing**: Handles various scan qualities
- **Confidence scoring**: Surface quality metrics for review

### Performance Tips
- **Batch processing**: Use CLI for multiple documents
- **Engine reuse**: Single `Extractor` instance processes multiple docs efficiently
- **Memory management**: Automatic cleanup of temporary files and resources

## Contributing

### Development Setup
```bash
make setup        # Initial setup
make clean        # Clean temporary files
make status       # Check environment
```

### Code Style
```bash
make format       # Format code (requires black)
make lint         # Lint code (requires flake8)
```

### Testing
```bash
make test-api     # Test API endpoints
```

## Limitations and Future Enhancements

### Current Limitations
- **Semantic extraction**: OCR detects layout but not document-specific fields (case numbers, dates, etc.)
- **Single-threaded processing**: API processes one document at a time
- **Local inference**: Requires local compute for Surya backend

### Potential Enhancements
- Field-level extraction for specific document types
- Parallel processing support
- Cloud OCR engine adapters (Google Vision, AWS Textract)
- Document preprocessing pipeline (deskew, denoise)
- WebSocket support for real-time processing updates
