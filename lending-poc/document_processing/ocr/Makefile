# OCR Text Extraction Project Makefile
# Simple commands for setup and running the OCR service

# Variables
PYTHON = python3.12
VENV_DIR = surya-env
VENV_PYTHON = $(VENV_DIR)/bin/python
VENV_PIP = $(VENV_DIR)/bin/pip
API_HOST = 0.0.0.0
API_PORT = 8000

# Default target
.DEFAULT_GOAL := help

.PHONY: help setup install clean cli api start-service status

help: ## Show this help message
	@echo "OCR Text Extraction Project Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make start-service  # Complete service setup and startup (recommended for first time)"
	@echo "  make setup          # Set up virtual environment and install dependencies"
	@echo "  make cli            # Run CLI tool on default input folder"
	@echo "  make api            # Start API server"

start-service: ## Complete service setup and startup (setup + install + start API server)
	@echo "🚀 Starting complete OCR service setup and startup..."
	@echo ""
	@echo "Step 1/4: Checking virtual environment..."
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "📦 Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV_DIR) || { echo "❌ Failed to create virtual environment. Is $(PYTHON) installed?"; exit 1; }; \
		echo "✅ Virtual environment created"; \
	else \
		echo "✅ Virtual environment exists"; \
	fi
	@echo ""
	@echo "Step 2/4: Upgrading pip..."
	@$(VENV_PIP) install --upgrade pip --quiet
	@echo "✅ Pip upgraded"
	@echo ""
	@echo "Step 3/4: Installing dependencies..."
	@$(VENV_PIP) install -r requirements.txt --quiet
	@echo "✅ Dependencies installed"
	@echo ""
	@echo "Step 4/4: Starting API server..."
	@echo ""
	@echo "🌐 OCR API Service Ready!"
	@echo "=================================="
	@echo "Server URL:      http://$(API_HOST):$(API_PORT)"
	@echo "API Docs:        http://$(API_HOST):$(API_PORT)/docs"
	@echo "Health Check:    http://$(API_HOST):$(API_PORT)/health"
	@echo "Upload Endpoint: http://$(API_HOST):$(API_PORT)/extract"
	@echo ""
	@echo "📝 Test the service:"
	@echo "curl -X POST http://$(API_HOST):$(API_PORT)/extract -F \"file=@your_document.pdf\""
	@echo ""
	@echo "Press Ctrl+C to stop the service"
	@echo "=================================="
	@$(VENV_PYTHON) -m uvicorn api:app --host $(API_HOST) --port $(API_PORT) --reload

setup: ## Create virtual environment and install all dependencies
	@echo "Setting up virtual environment..."
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	@echo "Setup complete! Virtual environment created at $(VENV_DIR)/"
	@echo "To activate: source $(VENV_DIR)/bin/activate"

install: ## Install/update dependencies in existing environment
	@echo "Installing dependencies..."
	$(VENV_PIP) install -r requirements.txt
	@echo "Dependencies updated!"

clean: ## Clean up temporary files and caches
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "Cleanup complete!"

cli: ## Run CLI tool on default input folder (extraction_input/)
	@echo "Running OCR extraction on default input folder..."
	$(VENV_PYTHON) main.py

cli-file: ## Run CLI tool on specific file (usage: make cli-file FILE=path/to/file.pdf)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make cli-file FILE=path/to/file.pdf"; \
		exit 1; \
	fi
	@echo "Processing file: $(FILE)"
	$(VENV_PYTHON) main.py "$(FILE)"

api: ## Start API server
	@echo "Starting OCR API server..."
	@echo "Server will be available at: http://$(API_HOST):$(API_PORT)"
	@echo "API docs at: http://$(API_HOST):$(API_PORT)/docs"
	@echo "Press Ctrl+C to stop"
	$(VENV_PYTHON) -m uvicorn api:app --host $(API_HOST) --port $(API_PORT)

status: ## Show project status and environment info
	@echo "OCR Text Extraction Project Status:"
	@echo "=================================="
	@echo ""
	@echo "Virtual Environment: $(VENV_DIR)/"
	@if [ -d "$(VENV_DIR)" ]; then \
		echo "✅ Virtual environment exists"; \
		echo "Python: $$($(VENV_PYTHON) --version 2>/dev/null || echo 'Not available')"; \
	else \
		echo "❌ Virtual environment not found (run 'make setup')"; \
	fi
	@echo ""
	@echo "Input folder: extraction_input/ ($(shell ls -1 extraction_input/ 2>/dev/null | wc -l | tr -d ' ') files)"
	@echo "Output folder: extraction_output/"
	@echo ""
	@echo "Supported formats: PDF, PNG, JPEG"
	@echo "Available engines: surya (default)"
	@echo ""
	@echo "Commands:"
	@echo "  CLI: make cli"
	@echo "  API: make api"