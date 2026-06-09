import os
import json
import duckdb
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import gradio as gr

# 📁 Configuración estructural de volúmenes permanentes
STORAGE_DIR = "/app/storage"
METADATA_FILE = os.path.join(STORAGE_DIR, "system_metadata.json")

os.makedirs(STORAGE_DIR, exist_ok=True)

# Inicializar FastAPI (Controlador maestro para peticiones remotas concurrentes vía HTTPFS)
app = FastAPI(title="Cyberpunk DuckDB SaaS Orchestrator")

# 🌍 APERTURA TOTAL DE CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 💾 Gestores de persistencia JSON (Inmunes a redespliegues)
def cargar_sistema():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            try: return json.load(f)
            except: return {"databases": {}, "tokens": {}, "logs": []}
    return {"databases": {}, "tokens": {}, "logs": []}

def guardar_sistema(data):
    with open(METADATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# 🌐 ENDPOINT MAESTRO: Transferencia asíncrona de bloques binarios (HTTPFS)
@app.get("/stream/{token}/{db_name}")
async def stream_database_httpfs(token: str, db_name: str):
    data = cargar_sistema()
    
    if token not in data["tokens"]:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token inválido o revocado")
        
    token_info = data["tokens"][token]
    if token_info["database"] != db_name:
        raise HTTPException(status_code=403, detail="Acceso denegado: Token no autorizado para esta BD")
        
    ruta_archivo = os.path.join(STORAGE_DIR, db_name)
    if not os.path.exists(ruta_archivo):
        raise HTTPException(status_code=404, detail="El archivo binario .duckdb solicitado no existe")
        
    data["logs"].append({
        "token": token,
        "usuario": token_info["usuario"],
        "database": db_name,
        "evento": "Petición HTTPFS Exitosa"
    })
    guardar_sistema(data)
    
    return FileResponse(ruta_archivo, media_type="application/octet-stream", filename=db_name)

# ⬇️ ENDPOINT DE DESCARGA PROTEGIDA POR CONTRASEÑA
@app.get("/download/{db_name}")
async def descargar_archivo_completo(db_name: str, password: str):
    data = cargar_sistema()
    if db_name not in data["databases"]:
        raise HTTPException(status_code=404, detail="Base de datos no registrada")
        
    if data["databases"][db_name]["password_descarga"] != password:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
        
    ruta_archivo = os.path.join(STORAGE_DIR, db_name)
    return FileResponse(ruta_archivo, media_type="application/octet-stream", filename=db_name)


# ⚙️ CONTROLADORES LOGICÓ-VISUALES
def procesar_subida_inicial(archivos):
    if not archivos:
        return gr.update(visible=False), "⚠️ No seleccionaste ningún archivo.", gr.update(choices=[])
    
    archivo = archivos[0]
    nombre_base = os.path.basename(archivo.name)
    
    if not nombre_base.endswith('.duckdb'):
        return gr.update(visible=False), "❌ Error crítico: Este sistema solo acepta extensiones de motor .duckdb", gr.update(choices=[])
        
    ruta_final = os.path.join(STORAGE_DIR, nombre_base)
    os.replace(archivo.name, ruta_final)
    
    data = cargar_sistema()
    dbs_actuales = list(data["databases"].keys()) + [nombre_base]
    
    return gr.update(visible=True), f"📥 Archivo '{nombre_base}' inyectado. Configura su contraseña maestra abajo para guardarlo.", gr.update(choices=list(set(dbs_actuales)), value=nombre_base)

def confirmar_configuracion_db(nombre_db, pwd_descarga):
    if not nombre_db or nombre_db == "No hay bases de datos seleccionadas":
        return "❌ Error: Selecciona o sube una base de datos válida primero."
    if not pwd_descarga:
        return "❌ Debes definir una contraseña obligatoria para proteger el archivo."
        
    data = cargar_sistema()
    ruta_db = os.path.join(STORAGE_DIR, nombre_db)
    
    tabla_detectada = "N/A"
    total_filas = 0
    
    try:
        con = duckdb.connect(ruta_db, read_only=True)
        tablas = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main';").fetchall()
        if tablas:
            tabla_detectada = tablas[0][0]
            count_res = con.execute(f"SELECT COUNT(*) FROM {tabla_detectada};").fetchone()
            total_filas = count_res[0]
        con.close()
    except Exception as e:
        print(f"Error indexando en caliente: {str(e)}")

    data["databases"][nombre_db] = {
        "password_descarga": pwd_descarga,
        "tabla_principal": tabla_detectada,
        "total_registros": f"{total_filas:,}",
        "peso": f"{os.path.getsize(ruta_db) / (1024*1024):.2f} MB"
    }
    guardar_sistema(data)
    return f"🔒 ¡Configuración Exitosa! La base de datos '{nombre_db}' ya está activa en tu Panel de Control."

def ejecutar_comando_consola(nombre_db, pwd_db, comando_sql):
    data = cargar_sistema()
    if not nombre_db or nombre_db not in data["databases"]:
        return "❌ Selecciona una base de datos activa."
    if data["databases"][nombre_db]["password_descarga"] != pwd_db:
        return "❌ Autenticación fallida: Contraseña de base de datos incorrecta."
        
    ruta_db = os.path.join(STORAGE_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=False)
        con.execute(comando_sql)
        con.close()
        return "⚡ Sentencia SQL inyectada y procesada de forma exitosa sobre el binario."
    except Exception as e:
        return f"❌ Error del motor SQL de DuckDB: {str(e)}"

def obtener_estructura_completa(nombre_db):
    data = cargar_sistema()
    if not nombre_db or nombre_db not in data["databases"]:
        return "Selecciona una base de datos primero."
        
    ruta_db = os.path.join(STORAGE_DIR, nombre_db)
    try:
        con = duckdb.connect(ruta_db, read_only=True)
        tabla = data["databases"][nombre_db]["tabla_principal"]
        if tabla != "N/A":
            info = con.execute(f"PRAGMA table_info('{tabla}');").fetchall()
            estructura = f"📋 Catálogo Estructural de Columnas para [{tabla}]:\n\n"
            for col in info:
                estructura += f" 🔹 Campo: {col[1].ljust(18)} | Tipo: {col[2]}\n"
        else:
            estructura = "No se detectaron tablas públicas estructuradas en el catálogo principal."
        con.close()
        return estructura
    except Exception as e:
        return f"❌ Falla al lanzar petición sobre la araña: {str(e)}"

def generar_key_consulta(nombre_db, pwd_db, nombre_usuario):
    if not nombre_usuario:
        return "❌ Introduce el nombre del usuario o bot asignado.", ""
    data = cargar_sistema()
    if not nombre_db or nombre_db not in data["databases"]:
        return "❌ Selecciona una base de datos válida.", ""
    if data["databases"][nombre_db]["password_descarga"] != pwd_db:
        return "❌ Autenticación fallida: Contraseña incorrecta.", ""
        
    nuevo_token = f"tkn_{uuid.uuid4().hex[:16]}"
    data["tokens"][nuevo_token] = {
        "usuario": nombre_usuario,
        "database": nombre_db
    }
    guardar_sistema(data)
    
    url_final = f"http://TU_DOMINIO_DOKPLOY.sslip.io/stream/{nuevo_token}/{nombre_db}"
    
    codigo_snip = (
        f"# Bloque de conexión remota optimizado con CORS libre para tu Bot externo\n"
        f"import duckdb\n\n"
        f"con = duckdb.connect(':memory:')\n"
        f"con.execute('INSTALL httpfs; LOAD httpfs;')\n"
        f"con.execute(\"SET enable_http_metadata_cache=true;\")\n\n"
        f"# Conexión por bloques binarios instantánea:\n"
        f"con.execute(\"ATTACH '{url_final}' AS remote_db (READ_ONLY);\")\n"
        f"print('¡Conexión remota exitosa con la base de datos estática!')\n"
    )
    return "✅ Token de consulta estructurado correctamente.", codigo_snip

def listar_usuarios_db(nombre_db):
    data = cargar_sistema()
    usuarios = []
    for tkn, info in data["tokens"].items():
        if info["database"] == nombre_db:
            usuarios.append(f"👤 Cliente: {info['usuario'].ljust(15)} | 🔑 Key Asignada: {tkn}")
    return "\n".join(usuarios) if usuarios else "No se registran credenciales de usuarios para este archivo binario."

def renderizar_logs_conexiones():
    data = cargar_sistema()
    if not data["logs"]:
        return "Sin tráfico registrado en la red actualmente."
    lineas = [f"📡 [Tráfico] Usuario: {l['usuario']} -> Base: {l['database']} ({l['evento']})" for l in data["logs"][-12:]]
    return "\n".join(reversed(lineas))

def actualizar_choices_db():
    data = cargar_sistema()
    choices = list(data["databases"].keys())
    return gr.update(choices=choices if choices else ["No hay bases de datos seleccionadas"])


# 🎨 COMPOSICIÓN DE LA INTERFAZ GRÁFICA CORREGIDA (Compatible con Gradio 5.x y 6.x)
with gr.Blocks(analytics_enabled=False, theme=gr.themes.Monochrome()) as ui:
    gr.Markdown("# 🌌 INTERFAZ DE CONTROL GENERAL: ORQUESTADOR DUCKDB SAAS")
    gr.Markdown("Controlador centralizado para inyección, tuning y distribución asíncrona de bases de datos estáticas.")
    
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### 📡 Conexiones de Red y Colección de Datos Globales")
            logs_box = gr.TextArea(value=renderizar_logs_conexiones(), label="Logs de Auditoría en Red (CORS Global Abierto)", interactive=False, lines=4)
            btn_refresh_logs = gr.Button("🔄 Refrescar Tráfico de Peticiones", size="sm")
            btn_refresh_logs.click(renderizar_logs_conexiones, outputs=[logs_box])
            
    with gr.Tab("📤 Carga Binaria e Inyección Rápida"):
        gr.Markdown("### 📥 Método de Transferencia por Bloques Binarios")
        uploader = gr.File(label="Arrastra tu base de datos masiva .duckdb aquí", file_types=[".duckdb"])
        btn_upload = gr.Button("🚀 Inyectar al Servidor Permanente", variant="primary")
        upload_log = gr.Textbox(label="Estado del Canal Físico de Carga", interactive=False)
        
        # 🛠️ SOLUCIÓN AL ERROR: Cambiado gr.Box por gr.Group (Estilo contenedor moderno)
        with gr.Group(visible=False) as modal_config:
            gr.Markdown("### ⚙️ Link de Configuración de Archivo Requerido")
            pwd_descarga_input = gr.Textbox(label="Establece la Contraseña de Descarga y Seguridad Maestra", type="password")
            btn_guardar_config = gr.Button("🔒 Confirmar Parámetros y Activar Tarjeta", variant="primary")
            config_status = gr.Textbox(label="Estado de Activación", interactive=False)
            
    with gr.Tab("🎴 Panel de Tarjetas e Infraestructura"):
        gr.Markdown("### 🃏 Cartas de Control de Bases de Datos Activas")
        
        with gr.Row():
            selector_db = gr.Dropdown(choices=list(cargar_sistema()["databases"].keys()), label="Selecciona la Base de Datos para inicializar los bracitos de acción")
            btn_refresh_dropdown = gr.Button("🔄 Refrescar Lista de Cartas", size="sm")
            
        btn_refresh_dropdown.click(actualizar_choices_db, outputs=[selector_db])
        
        # 🛠️ SOLUCIÓN AL ERROR: Cambiado gr.Box por gr.Group
        with gr.Group():
            info_meta = gr.Markdown("## 📭 Ninguna Base de Datos Desplegada\nSelecciona un archivo del menú superior para activar los controles asíncronos.")
            
            with gr.Tab("⚙️ Configuración (Comandos)"):
                gr.Markdown("#### ⚙️ Consola de optimización interna. Agrega o modifica índices en caliente.")
                pwd_admin = gr.Textbox(label="Contraseña Maestra de la Base de Datos", type="password")
                cmd_sql = gr.Textbox(label="Comando SQL Ejecutivo (ej: CREATE INDEX idx_dni ON personas (DNI);)")
                btn_sql = gr.Button("Ejecutar Query sobre el Binario", variant="primary")
                out_sql = gr.Textbox(label="Consola de Respuesta del Motor", interactive=False)
                
                btn_sql.click(ejecutar_comando_consola, inputs=[selector_db, pwd_admin, cmd_sql], outputs=[out_sql])
            
            with gr.Tab("🕷️ Estructura Física (Araña)"):
                gr.Markdown("#### 🕷️ Petición estructural automática al catálogo de metadatos.")
                btn_spider = gr.Button("🕸️ Lanzar Petición Estructural", variant="primary")
                out_spider = gr.TextArea(label="Mapeo de Esquema Binario Detectado", interactive=False)
                
                btn_spider.click(obtener_estructura_completa, inputs=[selector_db], outputs=[out_spider])
                
            with gr.Tab("🔑 Generar Key"):
                gr.Markdown("#### 🔑 Generación de tokens individuales de acceso por cliente con CORS abierto.")
                pwd_key = gr.Textbox(label="Contraseña Maestra de la Base de Datos", type="password")
                user_name = gr.Textbox(label="Identificador o Nombre del Usuario Beneficiario")
                btn_key = gr.Button("⚡ Generar Llave de Consulta Segura", variant="primary")
                out_key_status = gr.Textbox(label="Estado del Token", interactive=False)
                out_key_code = gr.TextArea(label="String de Conexión HTTPFS Completo para tu Bot", interactive=False)
                
                btn_key.click(generar_key_consulta, inputs=[selector_db, pwd_key, user_name], outputs=[out_key_status, out_key_code])
                
            with gr.Tab("👥 Usuarios Permitidos"):
                gr.Markdown("#### 👥 Visibilidad del Ecosistema: Consulta qué usuarios tienen llaves creadas.")
                btn_users = gr.Button("📋 Listar Usuarios Vinculados", variant="primary")
                out_users = gr.TextArea(label="Usuarios y Tokens activos para esta Base de Datos", interactive=False)
                
                btn_users.click(listar_usuarios_db, inputs=[selector_db], outputs=[out_users])

    def refrescar_cabecera_tarjeta(db):
        if not db or db == "No hay bases de datos seleccionadas":
            return "## 📭 Selecciona una base de datos válida."
        data = cargar_sistema()
        if db not in data["databases"]: 
            return "## ⚠️ Base de datos en proceso de configuración."
        info = data["databases"][db]
        return f"## 📊 Base de Datos Activa: `{db}`\n* **Peso en Disco:** {info['peso']} | **Tabla Principal:** {info['tabla_principal']} | **Total Registros:** {info['total_registros']}*"

    btn_upload.click(procesar_subida_inicial, inputs=[uploader], outputs=[modal_config, upload_log, selector_db])
    btn_guardar_config.click(confirmar_configuracion_db, inputs=[selector_db, pwd_descarga_input], outputs=[config_status])
    selector_db.change(refrescar_cabecera_tarjeta, inputs=[selector_db], outputs=[info_meta])

# Unificar la interfaz con FastAPI
app = gr.mount_gradio_app(app, ui, path="/")

if __name__ == "__main__":
    import uvicorn
    # Lanzamiento nativo en el puerto 7860 expuesto por el Dockerfile
    uvicorn.run(app, host="0.0.0.0", port=7860)
