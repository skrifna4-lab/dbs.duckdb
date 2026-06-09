FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias esenciales del sistema operativo para DuckDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias e instalarlas en las capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Crear los directorios fijos de almacenamiento de bases de datos binarias
RUN mkdir -p /app/storage/databases

# Copiar el motor de la API
COPY app.py .

# 🔐 VOLUMEN FIJO: Resguarda la carpeta física ante cualquier reinicio o cambio de código
VOLUME ["/app/storage"]

# Exponer el puerto de comunicación de tu backend
EXPOSE 8000

# Arrancar la API capturando los logs binarios de red de forma inmediata
CMD ["python", "-u", "app.py"]
