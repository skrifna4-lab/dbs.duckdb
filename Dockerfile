FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Directorios para bases de datos e imágenes dentro del volumen persistente
RUN mkdir -p /app/storage/databases /app/storage/images

COPY app.py .

VOLUME ["/app/storage"]

# Puerto del backend API
EXPOSE 8000

CMD ["python", "-u", "app.py"]
