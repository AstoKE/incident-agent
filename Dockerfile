FROM python:3.11-slim

WORKDIR /app

# System deps needed by chromadb (hnswlib build) and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and package manifest
COPY pyproject.toml .
COPY src/ src/

# Install the package itself (no extra deps, already installed above)
RUN pip install --no-cache-dir --no-deps -e .

# Sample logs (optional; override with a volume mount in docker-compose)
COPY data/ data/

ENV PYTHONPATH=src

CMD ["python", "-m", "incident_agent.app"]
