import os
import uuid
import shutil
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests
import duckdb

# 🧱 CONFIGURACIÓN DE RUTA INTERNA FIJA ADENTRO DEL CONTENEDOR DOCKER
STORAGE_DIR = "/app/storage"
DB_DIR = os.path.join(STORAGE_DIR, "databases")
os.makedirs(DB_DIR, exist_ok=True)

# 🔌 CREDENCIALES NATIVAS DE TU SUPABASE (VALIDADAS CON ÉXITO)
SUPABASE_URL = "http://skrifna-supabase-473c9f-192-129-183-187.sslip.io"
SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3ODEwMTQzOTksImV4cCI6MTg5MzQ1NjAwMCwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlzcyI6InN1cGFiYXNlIn0.L4hICENRSDn6FRSX1YDj0dxYrnmIjEPsieqvCW8VMj4"

# Headers maestros con firma válida para pasar los filtros de Kong
HEADERS_SUPABASE = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "apiKey": SERVICE_ROLE_KEY,
    "Content-Type": "application/json"
}

# =====================================================================
# 🔥 CREACIÓN AUTOMÁTICA DE TABLAS POR API (MÉTODO RPC DE SUPABASE)
# =====================================================================
def inicializar_tablas_desde_la_api():
    """
    Este bloque se ejecuta de forma obligatoria en el arranque del contenedor.
    Envía el script DDL de creación de tablas al endpoint RPC remoto.
    """
    print("⚡ [STARTUP] Conectando a la API REST de Supabase para asegurar la creación de las tablas...")
    url_rpc = f"{SUPABASE_URL}/rest/v1/rpc/ejecutar_sql_remoto"
    
    # Sentencias SQL estructuradas de forma limpia sin errores de sintaxis
    sql_script = """
    -- 1. Tabla de control de cartas (Bases de datos estáticas)
    CREATE TABLE IF NOT EXISTS public.metadata_dbs (
        nombre_db TEXT PRIMARY KEY,
        password_descarga TEXT NOT NULL,
        categoria TEXT DEFAULT 'General',
        imagen TEXT,
        tabla_principal TEXT,
        total_registros BIGINT,
        peso_mb REAL,
        configurada BOOLEAN DEFAULT true
    );

    -- 2. Tabla para almacenar los tokens autorizados por cliente
    CREATE TABLE IF NOT EXISTS public.metadata_tokens (
        token TEXT PRIMARY KEY,
        usuario TEXT NOT NULL,
        database TEXT NOT NULL
    );

    -- 3. Tabla de logs globales para auditoría de tráfico
    CREATE TABLE IF NOT EXISTS public.metadata_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        token TEXT,
        usuario TEXT,
        database TEXT,
        evento TEXT,
        fecha TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
    );
    """
    
    payload = {
        "query": sql_script
    }
    
    try:
        # Petición POST al RPC de la API REST para ejecutar el SQL en el servidor
        response = requests.post(url_rpc, headers=HEADERS_SUPABASE, json=payload, timeout=15)
        
        print("==================================================")
        if response.status_code in [200, 204]:
            print("🎉 [SUPABASE] Estructura creada o verificada de manera remota con éxito.")
            print(f"📡 Estado de Kong: Código HTTP {response.status_code} (Procesado)")
        else:
            print(f"❌ Falló el inyector automático de la DB (Código HTTP {response.status_code}):")
            print(f"📄 Respuesta del servidor: {response.text}")
        print("==================================================")
        
    except Exception as e:
        print(f"❌ [STARTUP_ERROR] Falla física de red al intentar inicializar tablas por API: {str(e)}")


# Manejador del ciclo de vida nativo de FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Forzar la verificación e inyección de tablas antes de aceptar tráfico HTTP
    inicializar_tablas_desde_la_api()
    yield

app = FastAPI(title="SaaS Orchestrator Core API", version="3.4.0", lifespan=lifespan)

# Mapear los headers con Prefer para el resto de endpoints REST estándar (PostgREST)
HEADERS_REST = HEADERS_SUPABASE.copy()
HEADERS_REST["Prefer"] = "return=representation"

# 🌍 APERTURA TOTAL DE CORS PARA TU FRONTEND HTML CYBERPUNK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================================
# 📡 CANAL EXCLUSIVO: TRANSMISIÓN BINARIA ASÍNCRONA (HTTPFS DUCKDB)
# =====================================================================
@app.get("/api/stream/{token}/{db_name}")
async def stream_database_httpfs(token: str, db_name: str):
    """Canal de comunicación asíncrono para tus bots externos. DuckDB httpfs consume este endpoint."""
    url_token = f"{SUPABASE_URL}/rest/v1/metadata_tokens?token=eq.{token}&select=usuario,database"
    try:
        res_token = requests.get(url_token, headers=HEADERS_REST, timeout=10)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de red con Supabase Auth Link: {str(e)}")
        
    if res_token.status_code != 200 or not res_token.json():
        raise HTTPException(status_code=403, detail="Acceso denegado: Token invalido o revocado")
        
    token_data = res_token.json()[0]
    usuario, authorized_db = token_data["usuario"], token_data["database"]
    
    if authorized_db != db_name:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token no autorizado para este archivo")
        
    ruta_real = os.path.join(DB_DIR, db_name)
    if not os.path.exists(ruta_real):
        raise HTTPException(status_code=404, detail="El archivo binario solicitado no existe en la ruta fija")
        
    log_payload = {"token": token, "usuario": usuario, "database": db_name, "evento": "Peticion HTTPFS Exitosa"}
    requests.post(f"{SUPABASE_URL}/rest/v1/metadata_logs", headers=HEADERS_REST, json=log_payload, timeout=5)
    
    return FileResponse(ruta_real, media_type="application/octet-stream", filename=db_name)


# =====================================================================
# 🛠️ ENDPOINTS API REST (RESPUESTAS 100% JSON PARA TU PANEL WEB)
# =====================================================================

@app.get("/api/system/path")
async def obtener_ruta_servidor():
    """
    🔍 INSPECTOR DE SISTEMA DINÁMICO:
    Averigua en tiempo de ejecución la ubicación física real y absoluta
    dentro del entorno donde está montado el sistema de archivos del contenedor.
    """
    try:
        path_real = Path(DB_DIR).resolve(strict=False)
        if not path_real.exists():
            path_real.mkdir(parents=True, exist_ok=True)
            
        return {
            "status": "success",
            "origen": "System OS Inspection (Dynamic)",
            "ruta_absoluta_sistema": str(path_real),
            "directorio_padre": str(path_real.parent),
            "existe_en_disco": path_real.is_dir()
        }
    except Exception as e:
        return {
            "status": "error",
            "detail": f"No se pudo auditar el sistema de archivos de forma dinámica: {str(e)}"
        }


@app.get("/api/database/scan")
async def escanear_archivos_nuevos():
    """🔍 ESCÁNER DE ARCHIVOS: Compara el disco contra Supabase y detecta si hay archivos .duckdb nuevos huérfanos."""
    archivos_en_disco = [f for f in os.listdir(DB_DIR) if f.endswith('.duckdb')]
    try:
        res_dbs = requests.get(f"{SUPABASE_URL}/rest/v1/metadata_dbs?select=nombre_db", headers=HEADERS_REST, timeout=10)
        lista_registradas = [r["nombre_db"] for r in res_dbs.json()] if res_dbs.status_code == 200 else []
    except:
        lista_registradas = []
    
    archivos_nuevos_sin_configurar = [arc for arc in archivos_en_disco if arc not in lista_registradas]
    
    return {
        "status": "success",
        "archivos_detectados_en_disco": archivos_en_disco,
        "nuevos_por_configurar": archivos_nuevos_sin_configurar
    }


@app.post("/api/database/upload-direct")
async def subida_http_directa(file: UploadFile = File(...)):
    """Soporta subidas HTTP directas para archivos estáticos más livianos."""
    if not file.filename.endswith('.duckdb'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .duckdb")
    ruta_destino = os.path.join(DB_DIR, file.filename)
    with open(ruta_destino, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "success", "message": f"Archivo {file.filename} inyectado por HTTP. Procede a configurarlo."}


@app.post("/api/database/configure")
async def configurar_y_memorizar_db(
    nombre_db: str = Form(...),
    password_descarga: str = Form(...),
    categoria: str = Form("General"),
    imagen_url: str = Form("")
):
    """📝 LINK DE CONFIGURACIÓN OBLIGATORIA: Analiza las tablas/filas de la base detectada y publica la tarjeta en Supabase."""
    ruta_real = os.path.join(DB_DIR, nombre_db)
    if not os.path.exists(ruta_real):
        raise HTTPException(status_code=404, detail="El archivo binario no se encuentra en el disco duro")

    tabla_detectada = "N/A"
    total_filas = 0
    try:
        con_fria = duckdb.connect(ruta_real, read_only=True)
        tablas = con_fria.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main';").fetchall()
        if tablas:
            tabla_detectada = tablas[0][0]
            total_filas = con_fria.execute(f"SELECT COUNT(*) FROM {tabla_detectada};").fetchone()[0]
        con_fria.close()
    except Exception as e:
        print(f"Error analizando cabeceras binarias: {str(e)}")

    peso_mb = round(os.path.getsize(ruta_real) / (1024 * 1024), 2)

    db_payload = {
        "nombre_db": nombre_db,
        "password_descarga": password_descarga,
        "categoria": categoria,
        "imagen": imagen_url,
        "tabla_principal": tabla_detectada,
        "total_registros": total_filas,
        "peso_mb": peso_mb,
        "configurada": True
    }
    
    headers_upsert = HEADERS_REST.copy()
    headers_upsert["Resolution"] = "merge-duplicates"
    requests.post(f"{SUPABASE_URL}/rest/v1/metadata_dbs", headers=headers_upsert, json=db_payload, timeout=10)

    return {
        "status": "success",
        "message": f"Base de datos '{nombre_db}' memorizada e indexada con éxito en tu Supabase",
        "analisis_estructural": {"tabla_maestra": tabla_detectada, "registros_totales": total_filas, "peso_detectado": f"{peso_mb} MB"}
    }


@app.get("/api/database/list")
async def listar_cartas_saas(categoria: Optional[str] = None):
    """Retorna todas las bases de datos registradas en formato JSON limpio para pintar tus tarjetas HTML."""
    url = f"{SUPABASE_URL}/rest/v1/metadata_dbs?select=nombre_db,categoria,imagen,tabla_principal,total_registros,peso_mb"
    if categoria:
        url += f"&categoria=ilike.{categoria}"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    cartas = res.json() if res.status_code == 200 else []
    return {"status": "success", "total_cartas": len(cartas), "databases": cartas}


@app.post("/api/database/console")
async def ejecutar_comando_sql(nombre_db: str = Form(...), password: str = Form(...), query: str = Form(...)):
    """⚙️ ICONO CONFIGURACIÓN: Consola para ejecutar sentencias de optimización (Indices/Vacuum) en caliente."""
    url_check = f"{SUPABASE_URL}/rest/v1/metadata_dbs?nombre_db=eq.{nombre_db}&select=password_descarga"
    res_check = requests.get(url_check, headers=HEADERS_REST, timeout=10)
    if res_check.status_code != 200 or not res_check.json() or res_check.json()[0]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña de base de datos incorrecta")
        
    ruta_db = os.path.join(DB_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=False)
        con.execute(query)
        con.close()
        return {"status": "success", "message": "Sentencia SQL ejecutada e inyectada con exito"}
    except Exception as e:
        return {"status": "error", "detail": f"Error en DuckDB: {str(e)}"}


@app.get("/api/database/spider/{nombre_db}")
async def araña_estructural(nombre_db: str):
    """🕷️ ICONO ARAÑA: Escanea y retorna las columnas y tipos de datos de la tabla interna de la tarjeta."""
    url = f"{SUPABASE_URL}/rest/v1/metadata_dbs?nombre_db=eq.{nombre_db}&select=tabla_principal"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    if res.status_code != 200 or not res.json() or res.json()[0]["tabla_principal"] == "N/A":
        return {"status": "success", "tabla": "N/A", "columnas": []}
        
    tabla = res.json()[0]["tabla_principal"]
    ruta_real = os.path.join(DB_DIR, nombre_db)
    try:
        con_db = duckdb.connect(ruta_real, read_only=True)
        pragma_info = con_db.execute(f"PRAGMA table_info('{tabla}');").fetchall()
        con_db.close()
        return {"status": "success", "tabla": tabla, "columnas": [{"campo": c[1], "tipo": c[2]} for c in pragma_info]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Spider: {str(e)}")


@app.post("/api/key/generate")
async def generar_token_acceso(nombre_db: str = Form(...), password: str = Form(...), usuario: str = Form(...)):
    """🔑 ICONO LLAVE: Valida credenciales de la tarjeta y guarda un nuevo token de consulta en Supabase."""
    url_check = f"{SUPABASE_URL}/rest/v1/metadata_dbs?nombre_db=eq.{nombre_db}&select=password_descarga"
    res_check = requests.get(url_check, headers=HEADERS_REST, timeout=10)
    if res_check.status_code != 200 or not res_check.json() or res_check.json()[0]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña de la base de datos incorrecta")
        
    nuevo_token = f"tkn_{uuid.uuid4().hex[:16]}"
    token_payload = {"token": nuevo_token, "usuario": usuario, "database": nombre_db}
    requests.post(f"{SUPABASE_URL}/rest/v1/metadata_tokens", headers=HEADERS_REST, json=token_payload, timeout=10)
    
    return {
        "status": "success",
        "token": nuevo_token,
        "usuario": usuario,
        "database": nombre_db,
        "url_httpfs_tubería": f"http://skrifna-duckdb-zokthr-c57021-192-129-183-187.sslip.io/api/stream/{nuevo_token}/{nombre_db}"
    }


@app.get("/api/key/users/{nombre_db}")
async def ver_usuarios_permitidos(nombre_db: str):
    """👥 PESTAÑA USUARIOS: Retorna el array JSON de todos los clientes autorizados de esta tarjeta."""
    url = f"{SUPABASE_URL}/rest/v1/metadata_tokens?database=eq.{nombre_db}&select=usuario,token"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    records = res.json() if res.status_code == 200 else []
    return {"status": "success", "database": nombre_db, "usuarios_autorizados": [{"usuario": r["usuario"], "token_key": r["token"]} for r in records]}


@app.get("/api/network/logs")
async def ver_logs_trafico_red():
    """📡 BARRA SUPERIOR (CONEXIONES): Devuelve el registro de auditoría en red directamente de tu Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/metadata_logs?select=token,usuario,database,evento,fecha&order=fecha.desc&limit=15"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    records = res.json() if res.status_code == 200 else []
    return {"status": "success", "conexiones_logs": [{"token": r["token"], "usuario": r["usuario"], "database": r["database"], "evento": r["evento"], "timestamp": r["fecha"]} for r in records]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
