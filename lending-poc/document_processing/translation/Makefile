.PHONY: setup install ollama api run

VENV       := .venv
PYTHON     := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
UVICORN    := $(VENV)/bin/uvicorn
PYTHON_BIN := python3.12

# Create venv and install all dependencies
setup:
	$(PYTHON_BIN) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "\nSetup complete. Run 'make ollama' then 'make api' to start."

# Install/sync dependencies if requirements.txt changes
install:
	$(PIP) install -r requirements.txt

# Start Ollama server (skips if already running)
ollama:
	@if pgrep -x "ollama" > /dev/null; then \
		echo "[ollama] Already running — skipping."; \
	else \
		echo "[ollama] Starting Ollama server…"; \
		ollama serve & \
		sleep 2; \
		echo "[ollama] Ollama server started."; \
	fi

# Start Ollama then the API server
api: ollama
	$(UVICORN) api_server:app --reload --port 8001

# Start Ollama then run the CLI batch translator
run: ollama
	$(PYTHON) run.py
