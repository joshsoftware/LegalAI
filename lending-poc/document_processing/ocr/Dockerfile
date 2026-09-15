FROM python:3.12-slim

WORKDIR /app

# Surya's recognition/layout models run in-process here. The LLM half runs
# in the separate surya-inference container, reached via SURYA_INFERENCE_URL
# — this image does not need llama-server.
#
# CPU by default: pin the CPU-only torch wheel so the image doesn't pull
# CUDA deps it can't use. Paired with the "gpu" compose profile, build with
# --build-arg GPU=1 to skip the pin and let requirements.txt's surya-ocr
# pull the default (CUDA-enabled) torch wheel instead — PyTorch's GPU wheels
# bundle their own CUDA runtime libs, so no CUDA base image is needed here,
# only GPU device access from the container (which the compose profile
# grants) and a host NVIDIA driver.
ARG GPU=0
RUN if [ "$GPU" = "0" ]; then \
      pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8010

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8010"]
