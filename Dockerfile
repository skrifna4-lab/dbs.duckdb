FROM python:3.11-slim

LABEL maintainer="Orchestrator Core API"
LABEL version="5.0.0"
LABEL description="DuckDB Remote Query Orchestrator — Volume Storage + Token Auth"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python (incluye duckdb)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código fuente
COPY app.py .

# Directorio de storage — será sobreescrito por el volumen Docker en runtime
# pero se crea aquí por si se corre sin compose
RUN mkdir -p /app/storage/databases

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/check || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
