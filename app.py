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

# 🧱 CONFIGURACIÓN DE RUTA INTERNA CORREGIDA SEGÚN EL RASTREO REAL DEL VPS
STORAGE_DIR = "/app/storage"
DB_DIR = os.path.join(STORAGE_DIR, "databases")  # 🎯 ¡CORREGIDO!: Mismo nombre de carpeta que tu volumen
os.makedirs(DB_DIR, exist_ok=True)

# 🔌 CREDENCIALES NATIVAS DE TU SUPABASE
SUPABASE_URL = "http://skrifna-supabase-473c9f-192-129-183-187.sslip.io"
SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3ODEwMTQzOTksImV4cCI6MTg5MzQ1NjAwMCwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlzcyI6InN1cGFiYXNlIn0.L4hICENRSDn6FRSX1YDj0dxYrnmIjEPsieqvCW8VMj4"

HEADERS_SUPABASE = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "apiKey": SERVICE_ROLE_KEY,
    "Content-Type": "application/json"
}

# =====================================================================
# 🔥 CREACIÓN AUTOMÁTICA DE TABLAS POR API (MÉTODO RPC DE SUPABASE)
# =====================================================================
def inicializar_tablas_desde_la_api():
    print("⚡ [STARTUP] Conectando a la API REST de Supabase para asegurar la creación de las tablas...")
    url_rpc = f"{SUPABASE_URL}/rest/v1/rpc/ejecutar_sql_remoto"
    
    sql_script = """
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

    CREATE TABLE IF NOT EXISTS public.metadata_tokens (
        token TEXT PRIMARY KEY,
        usuario TEXT NOT NULL,
        database TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS public.metadata_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        token TEXT,
        usuario TEXT,
        database TEXT,
        evento TEXT,
        fecha TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
    );
    """
    
    payload = {"query": sql_script}
    try:
        response = requests.post(url_rpc, headers=HEADERS_SUPABASE, json=payload, timeout=15)
        print("==================================================")
        if response.status_code in [200, 204]:
            print("🎉 [SUPABASE] Estructura creada o verificada de manera remota con éxito.")
        else:
            print(f"❌ Falló el inyector automático de la DB: {response.text}")
        print("==================================================")
    except Exception as e:
        print(f"❌ [STARTUP_ERROR] Falla de red en inicialización: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_tablas_desde_la_api()
    yield

app = FastAPI(title="SaaS Orchestrator Core API", version="3.5.0", lifespan=lifespan)

HEADERS_REST = HEADERS_SUPABASE.copy()
HEADERS_REST["Prefer"] = "return=representation"

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
# 🛠️ ENDPOINTS API REST (RESPUESTAS 100% JSON)
# =====================================================================

@app.get("/api/system/path")
async def obtener_ruta_servidor():
    try:
        path_real = Path(DB_DIR).resolve(strict=False)
        return {
            "status": "success",
            "origen": "System OS Inspection (Dynamic)",
            "ruta_absoluta_sistema": str(path_real),
            "directorio_padre": str(path_real.parent),
            "existe_en_disco": path_real.is_dir()
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/database/scan")
async def escanear_archivos_nuevos():
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


@app.post("/api/database/configure")
async def configurar_y_memorizar_db(
    nombre_db: str = Form(...),
    password_descarga: str = Form(...),
    categoria: str = Form("General"),
    imagen_url: str = Form("")
):
    ruta_real = os.path.join(DB_DIR, nombre_db)
    if not os.path.exists(ruta_real):
        raise HTTPException(status_code=404, detail=f"El archivo binario no se encuentra en {ruta_real}")

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
        "message": f"Base de datos '{nombre_db}' indexada con éxito",
        "analisis_estructural": {"tabla_maestra": tabla_detectada, "registros_totales": total_filas, "peso_detectado": f"{peso_mb} MB"}
    }


@app.get("/api/database/list")
async def listar_cartas_saas(categoria: Optional[str] = None):
    url = f"{SUPABASE_URL}/rest/v1/metadata_dbs?select=nombre_db,categoria,imagen,tabla_principal,total_registros,peso_mb"
    if categoria:
        url += f"&categoria=ilike.{categoria}"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    cartas = res.json() if res.status_code == 200 else []
    return {"status": "success", "total_cartas": len(cartas), "databases": cartas}


@app.post("/api/database/console")
async def ejecutar_comando_sql(nombre_db: str = Form(...), password: str = Form(...), query: str = Form(...)):
    url_check = f"{SUPABASE_URL}/rest/v1/metadata_dbs?nombre_db=eq.{nombre_db}&select=password_descarga"
    res_check = requests.get(url_check, headers=HEADERS_REST, timeout=10)
    if res_check.status_code != 200 or not res_check.json() or res_check.json()[0]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña de base de datos incorrecta")
        
    ruta_db = os.path.join(DB_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=False)
        con.execute(query)
        con.close()
        return {"status": "success", "message": "Sentencia SQL ejecutada"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/database/spider/{nombre_db}")
async def araña_estructural(nombre_db: str):
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/key/generate")
async def generar_token_acceso(nombre_db: str = Form(...), password: str = Form(...), usuario: str = Form(...)):
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
    url = f"{SUPABASE_URL}/rest/v1/metadata_tokens?database=eq.{nombre_db}&select=usuario,token"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    records = res.json() if res.status_code == 200 else []
    return {"status": "success", "database": nombre_db, "usuarios_autorizados": [{"usuario": r["usuario"], "token_key": r["token"]} for r in records]}


@app.get("/api/network/logs")
async def ver_logs_trafico_red():
    url = f"{SUPABASE_URL}/rest/v1/metadata_logs?select=token,usuario,database,evento,fecha&order=fecha.desc&limit=15"
    res = requests.get(url, headers=HEADERS_REST, timeout=10)
    records = res.json() if res.status_code == 200 else []
    return {"status": "success", "conexiones_logs": [{"token": r["token"], "usuario": r["usuario"], "database": r["database"], "evento": r["evento"], "timestamp": r["fecha"]} for r in records]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
