# Build stage
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime stage
FROM python:3.13-slim

WORKDIR /app

# Install runtime library dependencies (e.g. libsndfile for soundfile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

# Copy application code
COPY backend/ /app/backend/

# Create data directory for SQLite persistent volume
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
