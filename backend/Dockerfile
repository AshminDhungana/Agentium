# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agentium Backend Dockerfile
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARG PYTHON_DIGEST=sha256:f5cf0344c9886ff24d34797578d5d7dd6e8911ae0fe5962bb55d0f89603ec361
# Global ARG so it is in scope for the `FROM whisper-cpp-${WHISPER_BACKEND}` stage
# selector below. ARGs declared between stages are NOT visible to FROM instructions.
ARG WHISPER_BACKEND=cpu
FROM python:3.11-slim-bookworm@${PYTHON_DIGEST} AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    build-essential \
    libffi-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install numpy FIRST (required by torch and others)
RUN pip install --no-cache-dir numpy==1.26.4

# Install PyTorch with CPU support (SEPARATE - heavy package)
RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu

# Install heavy ML packages next (better layer caching)
RUN pip install --no-cache-dir sentence-transformers==3.3.1
# Bake the bge embedding model so it is NOT downloaded at runtime (HF_HUB_OFFLINE=1).
# (v1/MiniLM was retired.)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"
RUN pip install --no-cache-dir chromadb==0.5.23
RUN pip install --no-cache-dir tiktoken==0.8.0

# Copy and install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# whisper.cpp (CPU) ─────────────────────────────────────────────────────
# whisper.cpp builds with CMake (2026). The Makefile only has demo targets;
# "CUDA needs CMake". CPU build runs on any host (no GPU required).
FROM python:3.11-slim-bookworm AS whisper-cpp-cpu
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=base.en
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /whisper.cpp \
    && cd /whisper.cpp \
    && cmake -B build \
    && cmake --build build -j --config Release \
    && bash ./models/download-ggml-model.sh ${WHISPER_MODEL} \
    && mkdir -p /opt/whisper/models \
    && cp models/ggml-${WHISPER_MODEL}.bin /opt/whisper/models/ \
    && cp ./build/bin/whisper-cli /usr/local/bin/whisper-cli

# Ensure the CUDA-lib path exists so the runtime COPY from the selected src
# stage succeeds for the CPU variant (copies an empty dir — no bloat, no failure).
RUN mkdir -p /usr/local/cuda/lib64

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# whisper.cpp (CUDA, opt-in) ──────────────────────────────────────────
# Only used when WHISPER_BACKEND=cuda. Requires a GPU host run with
# --gpus all. A CUDA-compiled binary does NOT fall back to CPU.
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04 AS whisper-cpp-cuda
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=base.en
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /whisper.cpp \
    && cd /whisper.cpp \
    && cmake -B build -DGGML_CUDA=1 \
    && cmake --build build -j --config Release \
    && bash ./models/download-ggml-model.sh ${WHISPER_MODEL}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Production Stage
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FROM whisper-cpp-${WHISPER_BACKEND} AS whisper-cpp-src
FROM python:3.11-slim-bookworm@${PYTHON_DIGEST}

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"

# whisper.cpp runtime: whisper-cli + model (CPU default; CUDA uses same path but built differently)
COPY --from=whisper-cpp-src /usr/local/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=whisper-cpp-src /opt/whisper/models/ /opt/whisper/models/

# CUDA runtime .so files (real libs when WHISPER_BACKEND=cuda, empty dir when cpu)
COPY --from=whisper-cpp-src /usr/local/cuda/lib64/ /usr/local/cuda/lib64/

# Set working directory
WORKDIR /app

# Removed secure upload directory creation (now handled by object storage)
# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 agentium && \
    chown -R agentium:agentium /app
USER agentium

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD python -c "import http.client; conn = http.client.HTTPConnection('localhost', 8000); conn.request('GET', '/api/health'); resp = conn.getresponse(); exit(0 if resp.status == 200 else 1)" || exit 1

# Run application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]