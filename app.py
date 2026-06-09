import os
import uuid
import shutil
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import duckdb

# 🧱 CONFIGURACIÓN DE RUTA INTERNA FIJA ADENTRO DEL CONTENEDOR
STORAGE_DIR = "/app/storage"
DB_DIR = os.path.join(STORAGE_DIR, "databases")
os.makedirs(DB_DIR, exist_ok=True)

# 🔌 CREDENCIALES NATIVAS DE TU POSTGRESQL EN SUPABASE
DB_HOST = "db"             # Alias DNS interno en la red de tu Dokploy
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "zsalrelray6q3olo41iqasxlswe6lszx"

# Cadena de conexión estandarizada
CONN_STR_POSTGRES = f"dbname={DB_NAME} user={DB_USER} password={DB_PASS} host={DB_HOST} port={DB_PORT}"

app = FastAPI(title="SaaS Orchestrator Core API", version="3.0.0")

# 🌍 APERTURA TOTAL DE CORS PARA TU INTERFAZ GRÁFICA CYBERPUNK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def sincronizar_tablas_en_supabase():
    """Inicializa automáticamente la estructura relacional de metadatos dentro de tu Supabase."""
    try:
        con = duckdb.connect(':memory:')
        con.execute("INSTALL postgres; LOAD postgres;")
        
        # Tabla de cartas/bases de datos activas
        con.execute(f"CALL postgres_execute('{CONN_STR_POSTGRES}', 'CREATE TABLE IF NOT EXISTS metadata_dbs (nombre_db TEXT PRIMARY KEY, password_descarga TEXT, categoria TEXT, imagen TEXT, tabla_principal TEXT, total_registros BIGINT, peso_mb REAL, configurada BOOLEAN);')")
        # Tabla de tokens de acceso individuales asignados por cliente
        con.execute(f"CALL postgres_execute('{CONN_STR_POSTGRES}', 'CREATE TABLE IF NOT EXISTS metadata_tokens (token TEXT PRIMARY KEY, usuario TEXT, database TEXT);')")
        # Tabla de logs e historial de auditoría de conexiones globales
        con.execute(f"CALL postgres_execute('{CONN_STR_POSTGRES}', 'CREATE TABLE IF NOT EXISTS metadata_logs (id TEXT PRIMARY KEY, token TEXT, usuario TEXT, database TEXT, evento TEXT, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP);')")
        
        con.close()
        print("✅ Base de datos de Supabase sincronizada. Tablas de control listas.")
    except Exception as e:
        print(f"⚠️ Alerta en inicio al conectar con Supabase Postgres: {str(e)}")

# Correr inicializador atómico al levantar el backend
sincronizar_tablas_en_supabase()


# =====================================================================
# 📡 CANAL EXCLUSIVO: TRANSMISIÓN BINARIA ASÍNCRONA (HTTPFS DUCKDB)
# =====================================================================
@app.get("/api/stream/{token}/{db_name}")
async def stream_database_httpfs(token: str, db_name: str):
    """Soporta peticiones de rango HTTP. Permite a DuckDB httpfs consultar millones de filas en red."""
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    
    # Validar el token directo en Supabase Postgres
    token_check = con.execute(f"SELECT usuario, database FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_tokens') WHERE token = ?", [token]).fetchone()
    
    if not token_check:
        con.close()
        raise HTTPException(status_code=403, detail="Acceso denegado: Token invalido o revocado")
        
    usuario, authorized_db = token_check[0], token_check[1]
    if authorized_db != db_name:
        con.close()
        raise HTTPException(status_code=403, detail="Acceso denegado: Token sin autorizacion para este archivo")
        
    ruta_real = os.path.join(DB_DIR, db_name)
    if not os.path.exists(ruta_real):
        con.close()
        raise HTTPException(status_code=404, detail="El archivo binario solicitado no existe fisicamente en la ruta fija del contenedor")
        
    # Registrar log de auditoría en caliente directo en Supabase
    log_id = str(uuid.uuid4())
    con.execute(f"CALL postgres_execute('{CONN_STR_POSTGRES}', 'INSERT INTO metadata_logs (id, token, usuario, database, evento) VALUES (''{log_id}'', ''{token}'', ''{usuario}'', ''{db_name}'', ''Peticion HTTPFS Exitosa'');')")
    con.close()
    
    return FileResponse(ruta_real, media_type="application/octet-stream", filename=db_name)


# =====================================================================
# 🛠️ ENDPOINTS API REST (RESPUESTAS 100% JSON PARA TU PANEL WEB)
# =====================================================================

@app.get("/api/system/path")
async def obtener_ruta_servidor():
    """Retorna la ruta física absoluta para subir archivos pesados por SFTP sin adivinar."""
    return {
        "status": "success",
        "explicacion": "Apunta tu cliente SFTP/SSH a esta ruta exacta de tu VPS para inyectar bases de datos gigantes",
        "ruta_vps_fija_absoluta": "/var/lib/docker/volumes/supabase_storage-api/_data/databases/"
    }


@app.get("/api/database/scan")
async def escanear_archivos_nuevos():
    """🔍 ESCÁNER DE ARCHIVOS: Compara el disco contra Supabase y detecta bases de datos nuevas subidas por SFTP."""
    archivos_en_disco = [f for f in os.listdir(DB_DIR) if f.endswith('.duckdb')]
    
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    dbs_registradas = con.execute(f"SELECT nombre_db FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_dbs')").fetchall()
    con.close()
    
    lista_registradas = [r[0] for r in dbs_registradas]
    archivos_nuevos_sin_configurar = [arc for arc in archivos_en_disco if arc not in lista_registradas]
    
    return {
        "status": "success",
        "archivos_detectados_en_disco": archivos_en_disco,
        "nuevos_por_configurar": archivos_nuevos_sin_configurar
    }


@app.post("/api/database/upload-direct")
async def subida_http_directa(file: UploadFile = File(...)):
    """Soporta subidas HTTP directas para bases de datos estáticas más livianas."""
    if not file.filename.endswith('.duckdb'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .duckdb")
    
    ruta_destino = os.path.join(DB_DIR, file.filename)
    with open(ruta_destino, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"status": "success", "message": f"Archivo {file.filename} inyectado por HTTP. Pasa a configurarlo."}


@app.post("/api/database/configure")
async def configurar_y_memorizar_db(
    nombre_db: str = Form(...),
    password_descarga: str = Form(...),
    categoria: str = Form("General"),
    imagen_url: str = Form("")
):
    """📝 LINK DE CONFIGURACIÓN OBLIGATORIA: Analiza las tablas/filas de la base detectada y la publica en Supabase."""
    ruta_real = os.path.join(DB_DIR, nombre_db)
    if not os.path.exists(ruta_real):
        raise HTTPException(status_code=404, detail="El archivo binario no se encuentra en la carpeta física del disco")

    # Extraer metadatos estructurales automáticos abriendo el archivo en frío por un milisegundo
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

    # Insertar/Actualizar la configuración permanentemente en Supabase
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    query_insert = (
        f"CALL postgres_execute('{CONN_STR_POSTGRES}', 'INSERT INTO metadata_dbs "
        f"(nombre_db, password_descarga, categoria, imagen, tabla_principal, total_registros, peso_mb, configurada) "
        f"VALUES (''{nombre_db}'', ''{password_descarga}'', ''{categoria}'', ''{imagen_url}'', ''{tabla_detectada}'', {total_filas}, {peso_mb}, true) "
        f"ON CONFLICT (nombre_db) DO UPDATE SET password_descarga=EXCLUDED.password_descarga, categoria=EXCLUDED.categoria, imagen=EXCLUDED.imagen, total_registros={total_filas}, peso_mb={peso_mb};')"
    )
    con.execute(query_insert)
    con.close()

    return {
        "status": "success",
        "message": f"Base de datos '{nombre_db}' memorizada e indexada con éxito en Supabase",
        "analisis_estructural": {
            "tabla_maestra": tabla_detectada,
            "registros_totales": total_filas,
            "peso_detectado": f"{peso_mb} MB"
        }
    }


@app.get("/api/database/list")
async def listar_cartas_saas(categoria: Optional[str] = None):
    """Retorna todas las bases de datos registradas en formato JSON limpio para pintar tus tarjetas HTML."""
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    
    query = f"SELECT nombre_db, categoria, imagen, tabla_principal, total_registros, peso_mb FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_dbs')"
    records = con.execute(query).fetchall()
    con.close()
    
    cartas = []
    for r in records:
        if categoria and r[1].lower() != categoria.lower():
            continue
        cartas.append({
            "nombre_db": r[0],
            "categoria": r[1],
            "imagen": r[2],
            "tabla_principal": r[3],
            "total_registros": r[4],
            "peso_mb": r[5]
        })
        
    return {"status": "success", "total_cartas": len(cartas), "databases": cartas}


@app.post("/api/database/console")
async def ejecutar_comando_sql(nombre_db: str = Form(...), password: str = Form(...), query: str = Form(...)):
    """⚙️ ICONO CONFIGURACIÓN: Consola para ejecutar sentencias de optimización (Indices/Vacuum) en caliente."""
    con_check = duckdb.connect(':memory:')
    con_check.execute("INSTALL postgres; LOAD postgres;")
    res = con_check.execute(f"SELECT password_descarga FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_dbs') WHERE nombre_db = ?", [nombre_db]).fetchone()
    con_check.close()
    
    if not res or res[0] != password:
        raise HTTPException(status_code=401, detail="Contraseña de base de datos incorrecta")
        
    ruta_db = os.path.join(DB_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=False)
        con.execute(query)
        con.close()
        return {"status": "success", "message": "Sentencia SQL ejecutada e inyectada sobre el binario con exito"}
    except Exception as e:
        return {"status": "error", "detail": f"Error en ejecucion SQL de DuckDB: {str(e)}"}


@app.get("/api/database/spider/{nombre_db}")
async def araña_estructural(nombre_db: str):
    """🕷️ ICONO ARAÑA: Escanea y retorna las columnas y tipos de datos de la tabla interna de la tarjeta."""
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    res = con.execute(f"SELECT tabla_principal FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_dbs') WHERE nombre_db = ?", [nombre_db]).fetchone()
    con.close()
    
    if not res or res[0] == "N/A":
        return {"status": "success", "tabla": "N/A", "columnas": []}
        
    tabla = res[0]
    ruta_real = os.path.join(DB_DIR, nombre_db)
    
    try:
        con_db = duckdb.connect(ruta_real, read_only=True)
        pragma_info = con_db.execute(f"PRAGMA table_info('{tabla}');").fetchall()
        con_db.close()
        
        columnas = [{"campo": c[1], "tipo": c[2]} for c in pragma_info]
        return {"status": "success", "tabla": tabla, "columnas": columnas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error mapeando mapa binario (Spider): {str(e)}")


@app.post("/api/key/generate")
async def generar_token_acceso(nombre_db: str = Form(...), password: str = Form(...), usuario: str = Form(...)):
    """🔑 ICONO LLAVE: Valida credenciales de la tarjeta y guarda un nuevo token de consulta con CORS abierto."""
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    
    pwd_check = con.execute(f"SELECT password_descarga FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_dbs') WHERE nombre_db = ?", [nombre_db]).fetchone()
    
    if not pwd_check or pwd_check[0] != password:
        con.close()
        raise HTTPException(status_code=401, detail="Contraseña de la base de datos incorrecta")
        
    nuevo_token = f"tkn_{uuid.uuid4().hex[:16]}"
    con.execute(f"CALL postgres_execute('{CONN_STR_POSTGRES}', 'INSERT INTO metadata_tokens (token, usuario, database) VALUES (''{nuevo_token}'', ''{usuario}'', ''{nombre_db}'');')")
    con.close()
    
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
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    records = con.execute(f"SELECT usuario, token FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_tokens') WHERE database = ?", [nombre_db]).fetchall()
    con.close()
    
    usuarios = [{"usuario": r[0], "token_key": r[1]} for r in records]
    return {"status": "success", "database": nombre_db, "usuarios_autorizados": usuarios}


@app.get("/api/network/logs")
async def ver_logs_trafico_red():
    """📡 BARRA SUPERIOR (CONEXIONES): Devuelve el registro de auditoría en red directamente de Supabase."""
    con = duckdb.connect(':memory:')
    con.execute("INSTALL postgres; LOAD postgres;")
    records = con.execute(f"SELECT token, usuario, database, evento, fecha FROM postgres_scan('{CONN_STR_POSTGRES}', 'public', 'metadata_logs') ORDER BY fecha DESC LIMIT 15").fetchall()
    con.close()
    
    logs = [{"token": r[0], "usuario": r[1], "database": r[2], "evento": r[3], "timestamp": str(r[4])} for r in records]
    return {"status": "success", "total_peticiones_recientes": len(logs), "conexiones_logs": logs}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
