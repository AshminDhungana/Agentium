# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agentium Backend Dockerfile
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARG PYTHON_DIGEST=sha256:f5ef0344c9886ff24d34797578d5d7dd6e8911ae0fe5962bb55d0f89603ec361
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
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

# Install heavy ML packages next (better layer caching)
RUN pip install --no-cache-dir sentence-transformers==3.3.1
RUN pip install --no-cache-dir chromadb==0.5.23
RUN pip install --no-cache-dir tiktoken==0.8.0

# Copy and install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Production Stage
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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