FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema esenciales para DuckDB y SSH/SFTP si se requieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar librerías de Python requeridas
RUN pip install --no-cache-dir \
    gradio \
    duckdb \
    pandas \
    cryptography

# Crear el directorio donde se guardarán las bases de datos estáticas de forma persistente
RUN mkdir -p /app/storage

# Copiar el código fuente de la aplicación
COPY app.py .

# 🔐 CLAVE DE LA PERSISTENCIA: Declaramos este directorio como volumen. 
# Dokploy mantendrá todo lo que caiga aquí a salvo, sin importar si borras el contenedor.
VOLUME ["/app/storage"]

# Exponer el puerto nativo de la interfaz web de Gradio
EXPOSE 7860

# Ejecutar el panel de control
CMD ["python", "-u", "app.py"]
