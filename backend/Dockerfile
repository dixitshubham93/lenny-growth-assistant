FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for asyncpg + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .
# Copy the skills directory 
COPY skills/ ./skills/
# Copy the ingestion directory for indexing
COPY ingestion/ ./ingestion/

# Copy and set entrypoint
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
