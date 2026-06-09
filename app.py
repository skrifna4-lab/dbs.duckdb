import os
import json
import duckdb
import uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import gradio as gr

# 📁 Configuración del volumen persistente de tu Dockerfile
STORAGE_DIR = "/app/storage"
METADATA_FILE = os.path.join(STORAGE_DIR, "system_metadata.json")

os.makedirs(STORAGE_DIR, exist_ok=True)

# Inicializar FastAPI (Controlador de las peticiones HTTPFS concurrentes de tus bots externos)
app = FastAPI(title="Cyberpunk DuckDB Orchestrator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 Persistencia del estado global del sistema
def cargar_sistema():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            try: return json.load(f)
            except: return {"databases": {}, "tokens": {}, "logs": []}
    return {"databases": {}, "tokens": {}, "logs": []}

def guardar_sistema(data):
    with open(METADATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# 🌐 ENDPOINT DIRECTO DE TRANSFERENCIA BINARIA (HTTPFS)
@app.get("/stream/{token}/{db_name}")
async def stream_database_httpfs(token: str, db_name: str):
    """
    Soporta peticiones de rango HTTP (HTTP Range Requests).
    Permite que un DuckDB remoto lea solo los bloques binarios indexados que necesita en la consulta.
    """
    data = cargar_sistema()
    
    # Validar Token
    if token not in data["tokens"]:
        raise HTTPException(status_code=403, detail="Token inválido o revocado")
        
    token_info = data["tokens"][token]
    if token_info["database"] != db_name:
        raise HTTPException(status_code=403, detail="Este token no tiene autorización para esta base de datos")
        
    ruta_archivo = os.path.join(STORAGE_DIR, db_name)
    if not os.path.exists(ruta_archivo):
        raise HTTPException(status_code=404, detail="El archivo binario .duckdb no existe físicamente")
        
    # Registrar log de conexión
    data["logs"].append({
        "token": token,
        "usuario": token_info["usuario"],
        "database": db_name,
        "evento": "Lectura HTTPFS Bloques"
    })
    guardar_sistema(data)
    
    return FileResponse(ruta_archivo, media_type="application/octet-stream", filename=db_name)

# ⬇️ ENDPOINT DE DESCARGA SEGURA DEL ARCHIVO COMPLETO
@app.get("/download/{db_name}")
async def descargar_archivo_completo(db_name: str, password: str):
    """Permite la descarga directa si coincide la contraseña de descarga configurada."""
    data = cargar_sistema()
    if db_name not in data["databases"]:
        raise HTTPException(status_code=404, detail="Base de datos no registrada")
        
    if data["databases"][db_name]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña de descarga incorrecta")
        
    ruta_archivo = os.path.join(STORAGE_DIR, db_name)
    return FileResponse(ruta_archivo, media_type="application/octet-stream", filename=db_name)


# 🧠 LÓGICA DE NEGOCIO PARA CADA ACCIÓN DE LA INTERFAZ
def procesar_subida_inicial(archivos):
    if not archivos:
        return gr.update(visible=False), "⚠️ No seleccionaste ningún archivo."
    
    archivo = archivos[0] # Procesamos el archivo .duckdb principal
    nombre_base = os.path.basename(archivo.name)
    
    if not nombre_base.endswith('.duckdb'):
        return gr.update(visible=False), "❌ Error crítico: Este sistema solo acepta archivos con extensión nativa .duckdb"
        
    ruta_final = os.path.join(STORAGE_DIR, nombre_base)
    os.replace(archivo.name, ruta_final)
    
    # Abrir el modal/link de configuración obligatoria antes de mostrar la tarjeta
    return gr.update(visible=True), f"📥 Archivo '{nombre_base}' subido velozmente. Configura sus parámetros obligatorios abajo."

def confirmar_configuracion_db(nombre_db, pwd_descarga):
    if not pwd_descarga:
        return "❌ Debes definir una contraseña de protección para el archivo."
        
    data = cargar_sistema()
    
    # Extraer metadatos estructurales de forma automatizada en milisegundos
    ruta_db = os.path.join(STORAGE_DIR, nombre_db)
    tabla_detectada = "N/A"
    total_filas = 0
    
    try:
        con = duckdb.connect(ruta_db, read_only=True)
        tablas = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main';").fetchall()
        if tablas:
            tabla_detectada = tablas[0][0]
            total_filas = con.execute(f"SELECT COUNT(*) FROM {tabla_detectada};").fetchone()[0]
        con.close()
    except Exception as e:
        print(f"Error indexando: {str(e)}")

    data["databases"][nombre_db] = {
        "password_descarga": pwd_descarga,
        "tabla_principal": tabla_detectada,
        "total_registros": f"{total_filas:,}",
        "peso": f"{os.path.getsize(ruta_db) / (1024*1024):.2f} MB"
    }
    guardar_sistema(data)
    return f"✅ Base de datos '{nombre_db}' configurada y lista en el ecosistema."

def ejecutar_comando_consola(nombre_db, pwd_db, comando_sql):
    """⚙️ ICONO CONFIGURACIÓN: Ejecuta sentencias nativas (CREAR ÍNDICES, ALTERAR TABLAS)."""
    data = cargar_sistema()
    if nombre_db not in data["databases"] or data["databases"][nombre_db]["password_descarga"] != pwd_db:
        return "❌ Error: Contraseña de base de datos incorrecta."
        
    ruta_db = os.path.join(STORAGE_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=False)
        con.execute(comando_sql)
        con.close()
        return "⚡ Comando SQL ejecutado de forma exitosa sobre el binario."
    except Exception as e:
        return f"❌ Error SQL: {str(e)}"

def obtener_estructura_completa(nombre_db):
    """🕷️ ICONO ARAÑA/PIRÁMIDE: Obtiene el catálogo y las columnas del archivo."""
    data = cargar_sistema()
    if nombre_db not in data["databases"]:
        return "No hay datos."
        
    ruta_db = os.path.join(STORAGE_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=True)
        tabla = data["databases"][nombre_db]["tabla_principal"]
        if tabla != "N/A":
            info = con.execute(f"PRAGMA table_info('{tabla}');").fetchall()
            estructura = f"📋 Estructura Física de la Tabla [{tabla}]:\n\n"
            for col in info:
                estructura += f" -> Campo: {col[1]} | Tipo de Dato: {col[2]}\n"
        else:
            estructura = "El archivo no contiene tablas legibles en el esquema principal."
        con.close()
        return estructura
    except Exception as e:
        return f"❌ Fallo al escanear la araña estructural: {str(e)}"

def generar_key_consulta(nombre_db, pwd_db, nombre_usuario):
    """🔑 ICONO LLAVE: Valida la contraseña maestra y asocia un nuevo usuario al ecosistema."""
    if not nombre_usuario:
        return "❌ Ingresa el nombre del usuario asignado.", ""
        
    data = cargar_sistema()
    if nombre_db not in data["databases"] or data["databases"][nombre_db]["password_descarga"] != pwd_db:
        return "❌ Autenticación fallida: Contraseña de la base de datos incorrecta.", ""
        
    nuevo_token = f"tkn_{uuid.uuid4().hex[:16]}"
    data["tokens"][nuevo_token] = {
        "usuario": nombre_usuario,
        "database": nombre_db
    }
    guardar_sistema(data)
    
    url_final = f"http://TU_DOMINIO_DOKPLOY.sslip.io/stream/{nuevo_token}/{nombre_db}"
    
    codigo_snip = (
        f"# Copia este bloque en tu bot de Python externo con CORS abierto\n"
        f"import duckdb\n"
        f"con = duckdb.connect(':memory:')\n"
        f"con.execute('INSTALL httpfs; LOAD httpfs;')\n"
        f"con.execute(\"ATTACH '{url_final}' AS remote_db (READ_ONLY);\")\n"
    )
    return "✅ Token generado correctamente.", codigo_snip

def listar_usuarios_db(nombre_db):
    """👥 VISUALIZADOR INTERNO: Lista de usuarios vinculados a este archivo."""
    data = cargar_sistema()
    usuarios = []
    for tkn, info in data["tokens"].items():
        if info["database"] == nombre_db:
            usuarios.append(f"👤 {info['usuario']} | Clave Token: {tkn}")
    return "\n".join(usuarios) if usuarios else "No hay usuarios registrados para este archivo estático."

def renderizar_logs_conexiones():
    """📡 SECCIÓN SUPERIOR: Colección de peticiones globales en caliente."""
    data = cargar_sistema()
    if not data["logs"]:
        return "Sin solicitudes registradas en red."
    lineas = [f"📡 [Petición] Usuario: {l['usuario']} -> Base: {l['database']} ({l['evento']})" for l in data["logs"][-15:]]
    return "\n".join(reversed(lineas))


# 🎨 COMPOSICIÓN DE LA INTERFAZ GRÁFICA (Estilo Monocromático Oscuro Cyberpunk)
with gr.Blocks(title="Cyberpunk Base Engine", theme=gr.themes.Monochrome()) as ui:
    gr.Markdown("# 🌌 CYBERPUNK DUCKDB ORCHESTRATOR SAAS")
    
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### 📡 Conexiones y Solicitudes de Red en Tiempo Real")
            logs_box = gr.TextArea(value=renderizar_logs_conexiones(), label="Colección de peticiones globales (Auditoría CORS)", interactive=False, lines=4)
            btn_refresh_logs = gr.Button("🔄 Refrescar Tráfico de Red", size="sm")
            btn_refresh_logs.click(renderizar_logs_conexiones, outputs=[logs_box])
            
    with gr.Tab("📤 Carga Binaria HTTPFSP"):
        uploader = gr.File(label="Arrastra un archivo único .duckdb masivo", file_types=[".duckdb"])
        btn_upload = gr.Button("🚀 Inyectar al Servidor Remoto", variant="primary")
        upload_log = gr.Textbox(label="Log del Estado de Transferencia", interactive=False)
        
        # 🔗 Enlace con el modal obligatorio de configuración
        with gr.Box(visible=False) as modal_config:
            gr.Markdown("## ⚙️ Link de Configuración Obligatoria")
            gr.Markdown("Establece los parámetros de protección antes de indexar el archivo al público.")
            pwd_descarga_input = gr.Textbox(label="Contraseña Maestra de la Base de Datos (Seguridad/Descargas)", type="password")
            btn_guardar_config = gr.Button("🔒 Aplicar Parámetros y Activar Tarjeta", variant="primary")
            config_status = gr.Textbox(interactive=False)
            
        btn_upload.click(procesar_subida_inicial, inputs=[uploader], outputs=[modal_config, upload_log])

    with gr.Tab("🎴 Panel de Control General"):
        gr.Markdown("### 🃏 Cartas de Control de Bases de Datos Activas")
        
        # Para pruebas dinámicas, seleccionamos la base que queremos administrar en la tarjeta
        def obtener_dbs():
            return list(cargar_sistema()["databases"].keys())
            
        selector_db = gr.Dropdown(choices=obtener_dbs(), label="Selecciona la carta de base de datos a desplegar")
        btn_cargar_carta = gr.Button("👁️ Desplegar Carta Seleccionada")
        
        with gr.Box():
            info_meta = gr.Markdown("Selecciona una base de datos arriba para inicializar los bracitos de control.")
            
            with gr.Row():
                # ⚙️ Acción 1: Configuración / Comandos
                with gr.Tab("⚙️ Configuración (Comandos)"):
                    gr.Markdown("#### Modificar o agregar índices directo en caliente sobre el binario.")
                    pwd_admin = gr.Textbox(label="Contraseña de la Base de Datos", type="password")
                    cmd_sql = gr.Textbox(label="Comando SQL (ej: CREATE INDEX idx_dni ON personas (DNI);)")
                    btn_sql = gr.Button("Ejecutar Query de Optimización")
                    out_sql = gr.Textbox(label="Resultado Consola")
                    
                    btn_sql.click(ejecutar_comando_consola, inputs=[selector_db, pwd_admin, cmd_sql], outputs=[out_sql])
                
                # 🕷️ Acción 2: Estructura de la Araña
                with gr.Tab("🕷️ Estructura Físcia"):
                    gr.Markdown("#### Petición directa al catálogo para mapear el esquema completo de columnas.")
                    btn_spider = gr.Button("🕸️ Lanzar Petición Estructural")
                    out_spider = gr.TextArea(label="Esquema Binario Detectado")
                    
                    btn_spider.click(obtener_estructura_completa, inputs=[selector_db], outputs=[out_spider])
                    
                # 🔑 Acción 3: Generador de Llaves de Consulta
                with gr.Tab("🔑 Generar Key"):
                    gr.Markdown("#### Genera un token individual asignado a un usuario con CORS abierto.")
                    pwd_key = gr.Textbox(label="Contraseña de la Base de Datos", type="password")
                    user_name = gr.Textbox(label="Nombre del Usuario Destinatario")
                    btn_key = gr.Button("⚡ Generar Llave de Consulta")
                    out_key_status = gr.Textbox(label="Estado")
                    out_key_code = gr.TextArea(label="String de Conexión HTTPFS para el Bot")
                    
                    btn_key.click(generar_key_consulta, inputs=[selector_db, pwd_key, user_name], outputs=[out_key_status, out_key_code])
                    
                # 👥 Acción 4: Usuarios del Sistema
                with gr.Tab("👥 Usuarios Permitidos"):
                    gr.Markdown("#### Lista de credenciales y clientes autorizados que contienen acceso activo.")
                    btn_users = gr.Button("📋 Listar Usuarios Vinculados")
                    out_users = gr.TextArea(label="Usuarios autorizados de este archivo")
                    
                    btn_users.click(listar_usuarios_db, inputs=[selector_db], outputs=[out_users])

        # Lógica para rellenar la cabecera de la tarjeta seleccionada
        def refrescar_carta(db):
            data = cargar_sistema()
            if db not in data["databases"]: return "No encontrada."
            db_info = data["databases"][db]
            return f"## 📊 {db}\n* **Peso:** {db_info['peso']} | **Tabla:** {db_info['tabla_principal']} | **Filas:** {db_info['total_registros']}*"
            
        btn_cargar_carta.click(refrescar_carta, inputs=[selector_db], outputs=[info_meta])
        btn_guardar_config.click(confirmar_configuracion_db, inputs=[selector_db, pwd_descarga_input], outputs=[config_status])

# Fusionar la interfaz con FastAPI
app = gr.mount_gradio_app(app, ui, path="/")

if __name__ == "__main__":
    import uvicorn
    # Lanzamiento en el puerto expuesto del contenedor
    uvicorn.run(app, host="0.0.0.0", port=7860)
