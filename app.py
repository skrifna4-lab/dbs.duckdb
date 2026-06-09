import os
import json
import duckdb
import uuid
import shutil
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 📁 Configuración del volumen persistente de Docker
STORAGE_DIR = "/app/storage"
DB_DIR = os.path.join(STORAGE_DIR, "databases")
IMG_DIR = os.path.join(STORAGE_DIR, "images")
METADATA_FILE = os.path.join(STORAGE_DIR, "system_metadata.json")

# Asegurar directorios limpios
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

app = FastAPI(title="Core SaaS DuckDB API", version="2.0.0")

# 🌍 CORS TOTAL Abierto para que tu interfaz se conecte desde cualquier frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🖼️ Servir las imágenes subidas de forma estática para que tu interfaz pueda pintarlas usando URLs
app.mount("/static-images", StaticFiles(directory=IMG_DIR), name="images")

# 💾 Gestor del estado e indexación del volumen (Inmune a reinicios)
def cargar_sistema():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            try: return json.load(f)
            except: return {"databases": {}, "tokens": {}, "logs": []}
    return {"databases": {}, "tokens": {}, "logs": []}

def guardar_sistema(data):
    with open(METADATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


# =====================================================================
# 🌐 ENDPOINT DE TRANSFERENCIA BINARIA POR BLOQUES (HTTPFS DUCKDB)
# =====================================================================
@app.get("/api/stream/{token}/{db_name}")
async def stream_database_httpfs(token: str, db_name: str):
    """Soporta peticiones de rango HTTP. Es el core del método veloz HTTPFS."""
    data = cargar_sistema()
    
    if token not in data["tokens"]:
        raise HTTPException(status_code=403, detail="Token invalido o revocado")
        
    token_info = data["tokens"][token]
    if token_info["database"] != db_name:
        raise HTTPException(status_code=403, detail="Token sin autorizacion para esta base de datos")
        
    ruta_archivo = os.path.join(DB_DIR, db_name)
    if not os.path.exists(ruta_archivo):
        raise HTTPException(status_code=404, detail="El archivo binario .duckdb no existe")
        
    # Registrar log de auditoría
    data["logs"].append({
        "token": token,
        "usuario": token_info["usuario"],
        "database": db_name,
        "evento": "Peticion HTTPFS exitosa"
    })
    guardar_sistema(data)
    
    return FileResponse(ruta_archivo, media_type="application/octet-stream", filename=db_name)


# =====================================================================
# 🛠️ ENDPOINTS DEL BACKEND (RESPUESTAS EN JSON PURO PARA TU INTERFAZ)
# =====================================================================

@app.post("/api/database/upload")
async def subir_e_indexar_db(
    file: UploadFile = File(...),
    password_descarga: str = Form(...),
    categoria: str = Form("General"),
    imagen_url: Optional[str] = Form(None),
    imagen_file: Optional[UploadFile] = File(None)
):
    """
    Inyecta el archivo .duckdb, valida la extensión, procesa la imagen
    (sea por link o subida física), extrae los metadatos y guarda todo en JSON.
    """
    if not file.filename.endswith('.duckdb'):
        raise HTTPException(status_code=400, detail="El sistema solo acepta archivos con extension nativa .duckdb")
        
    data = cargar_sistema()
    nombre_db = file.filename
    ruta_final_db = os.path.join(DB_DIR, nombre_db)
    
    # 🚀 Guardado veloz del binario
    with open(ruta_final_db, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Procesar Imagen (Prioridad: Archivo subido > URL por Link)
    url_final_imagen = imagen_url or ""
    if imagen_file and imagen_file.filename:
        ext = os.path.splitext(imagen_file.filename)[1]
        nombre_img_seguro = f"{uuid.uuid4().hex}{ext}"
        ruta_final_img = os.path.join(IMG_DIR, nombre_img_seguro)
        
        with open(ruta_final_img, "wb") as buffer:
            shutil.copyfileobj(imagen_file.file, buffer)
        # Tu interfaz podrá llamar a la imagen usando esta ruta relativa del servidor
        url_final_imagen = f"/static-images/{nombre_img_seguro}"

    # Escaneo y conteo automático de registros internos usando DuckDB nativo
    tabla_detectada = "N/A"
    total_filas = 0
    try:
        con = duckdb.connect(ruta_final_db, read_only=True)
        tablas = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main';").fetchall()
        if tablas:
            tabla_detectada = tablas[0][0]
            total_filas = con.execute(f"SELECT COUNT(*) FROM {tabla_detectada};").fetchone()[0]
        con.close()
    except Exception as e:
        print(f"Error extrayendo estructura: {str(e)}")

    # Indexar la base de datos en los metadatos JSON organizados por categorías
    data["databases"][nombre_db] = {
        "password_descarga": password_descarga,
        "categoria": categoria,
        "imagen": url_final_imagen,
        "tabla_principal": tabla_detectada,
        "total_registros": total_filas,
        "peso_mb": round(os.path.getsize(ruta_final_db) / (1024*1024), 2)
    }
    guardar_sistema(data)
    
    return {
        "status": "success",
        "message": f"Base de datos {nombre_db} configurada correctamente",
        "metadata": data["databases"][nombre_db]
    }


@app.get("/api/database/list")
async def listar_bases_de_datos(categoria: Optional[str] = None):
    """Devuelve la lista completa de cartas/bases de datos en JSON, filtrable por categoria."""
    data = cargar_sistema()
    dbs = data["databases"]
    
    if categoria:
        # Filtramos el diccionario en base a la categoría que mande tu interfaz
        dbs = {k: v for k, v in dbs.items() if v["categoria"].lower() == categoria.lower()}
        
    return {"status": "success", "total": len(dbs), "databases": dbs}


@app.post("/api/database/console")
async def ejecutar_comando_sql(nombre_db: str = Form(...), password: str = Form(...), query: str = Form(...)):
    """⚙️ ICONO CONFIGURACIÓN: Ejecuta comandos (Tunear índices, borrar datos) y devuelve JSON."""
    data = cargar_sistema()
    if nombre_db not in data["databases"]:
        raise HTTPException(status_code=404, detail="Base de datos no registrada")
    if data["databases"][nombre_db]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
        
    ruta_db = os.path.join(DB_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=False)
        con.execute(query)
        con.close()
        return {"status": "success", "message": "Query procesada y guardada en el binario con exito"}
    except Exception as e:
        return {"status": "error", "detail": f"Error SQL: {str(e)}"}


@app.get("/api/database/spider/{nombre_db}")
async def araña_estructural(nombre_db: str):
    """🕷️ ICONO ARAÑA: Devuelve el esquema binario completo de columnas de la tabla principal en JSON."""
    data = cargar_sistema()
    if nombre_db not in data["databases"]:
        raise HTTPException(status_code=404, detail="Base de datos no registrada")
        
    ruta_db = os.path.join(DB_DIR, nombre_db)
    tabla = data["databases"][nombre_db]["tabla_principal"]
    
    if tabla == "N/A":
        return {"status": "success", "tabla": "N/A", "columnas": []}
        
    try:
        con = duckdb.connect(ruta_db, read_only=True)
        pragma_info = con.execute(f"PRAGMA table_info('{tabla}');").fetchall()
        con.close()
        
        columnas_json = [{"cid": c[0], "name": c[1], "type": c[2]} for c in pragma_info]
        return {"status": "success", "tabla": tabla, "columnas": columnas_json}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer estructura: {str(e)}")


@app.post("/api/key/generate")
async def generar_llave_acceso(nombre_db: str = Form(...), password: str = Form(...), usuario: str = Form(...)):
    """🔑 ICONO LLAVE: Valida credenciales de la tarjeta y retorna el Token y string de conexion en JSON."""
    data = cargar_sistema()
    if nombre_db not in data["databases"]:
        raise HTTPException(status_code=404, detail="Base de datos no encontrada")
    if data["databases"][nombre_db]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña maestra incorrecta")
        
    nuevo_token = f"tkn_{uuid.uuid4().hex[:16]}"
    data["tokens"][nuevo_token] = {
        "usuario": usuario,
        "database": nombre_db
    }
    guardar_sistema(data)
    
    # URL que usará el bot externo para conectarse
    url_stream = f"/api/stream/{nuevo_token}/{nombre_db}"
    
    return {
        "status": "success",
        "token": nuevo_token,
        "usuario": usuario,
        "database": nombre_db,
        "endpoint_stream_path": url_stream
    }


@app.get("/api/key/users/{nombre_db}")
async def listar_usuarios_autorizados(nombre_db: str):
    """👥 PESTAÑA USUARIOS: Retorna el array JSON de todas las llaves y personas atadas a esa carta."""
    data = cargar_sistema()
    usuarios_vinculados = []
    
    for token, info in data["tokens"].items():
        if info["database"] == nombre_db:
            usuarios_vinculados.append({
                "usuario": info["usuario"],
                "token": token
            })
            
    return {"status": "success", "database": nombre_db, "users": usuarios_vinculados}


@app.get("/api/network/logs")
async def ver_logs_trafico_red():
    """📡 BARRA SUPERIOR: Devuelve las ultimas 20 peticiones registradas de auditoria en JSON."""
    data = cargar_sistema()
    return {"status": "success", "logs": data["logs"][-20:]}

if __name__ == "__main__":
    import uvicorn
    # Lanzar FastAPI puro en el puerto 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
