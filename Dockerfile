FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias esenciales del sistema para DuckDB y compilaciones atómicas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar los requerimientos optimizando la caché de pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Crear el directorio raíz para el volumen de datos permanente
RUN mkdir -p /app/storage

# Copiar el backend de control central
COPY app.py .

# 🔐 INMUNIDAD DE VOLUMEN: Mapeo nativo para resguardar la información ante reinicios
VOLUME ["/app/storage"]

# Exponer el puerto de transmisión masiva e interfaz gráfica unificada
EXPOSE 7860

# Ejecutar el script en modo unbuffered para capturar los logs binarios de red al instante
CMD ["python", "-u", "app.py"]
