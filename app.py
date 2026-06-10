
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import requests, os, json, secrets, duckdb
from datetime import datetime

app = FastAPI(title="DuckDB Orchestrator API", version="5.0.0")

# ─────────────────────────────────────────────────────────────
# CONFIG CENTRAL
# ─────────────────────────────────────────────────────────────
SUPABASE_URL     = "http://skrifna-supabase-473c9f-192-129-183-187.sslip.io"
SERVICE_ROLE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpYXQiOjE3ODEwMTQzOTksImV4cCI6MTg5MzQ1NjAwMCwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlzcyI6InN1cGFiYXNlIn0"
    ".L4hICENRSDn6FRSX1YDj0dxYrnmIjEPsieqvCW8VMj4"
)

# Volumen Docker — aquí viven TODOS los archivos .duckdb
STORAGE_DIR = "/app/storage/databases"
os.makedirs(STORAGE_DIR, exist_ok=True)

HEADERS = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "apiKey": SERVICE_ROLE_KEY,
    "Content-Type": "application/json",
}

# ─────────────────────────────────────────────────────────────
# HELPERS SUPABASE  (solo catálogo + tokens, NUNCA archivos)
# ─────────────────────────────────────────────────────────────
def sb_get(tabla, qs="?select=*"):
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}{qs}", headers=HEADERS, timeout=8)
        return r.json() if r.ok else []
    except:
        return []

def sb_post(tabla, payload):
    h = {**HEADERS, "Prefer": "return=representation"}
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=h, json=payload, timeout=8)
        return r.status_code, r.json() if r.text else {}
    except Exception as e:
        return 500, {"error": str(e)}

def sb_patch(tabla, qs, payload):
    h = {**HEADERS, "Prefer": "return=representation"}
    try:
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/{tabla}{qs}", headers=h, json=payload, timeout=8)
        return r.status_code, r.json() if r.text else {}
    except Exception as e:
        return 500, {"error": str(e)}

def ejecutar_sql(query):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/sql", headers=HEADERS, json={"query": query}, timeout=10)
    if r.status_code == 404:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/rpc/ejecutar_sql_remoto", headers=HEADERS, json={"query": query}, timeout=10)
    return r.status_code, r.text

# ─────────────────────────────────────────────────────────────
# HELPER: resolver token → info db
# ─────────────────────────────────────────────────────────────
def resolver_token(token: str):
    """Devuelve (token_row, db_row) o lanza HTTPException."""
    tokens = sb_get("catalog_tokens", f"?token=eq.{token}&activo=eq.true&select=*")
    if not isinstance(tokens, list) or not tokens:
        raise HTTPException(401, "Token inválido o inactivo")
    tk = tokens[0]
    dbs = sb_get("catalog_dbs", f"?id=eq.{tk['db_id']}&select=*")
    if not isinstance(dbs, list) or not dbs:
        raise HTTPException(404, "Base de datos no encontrada para este token")
    return tk, dbs[0]


# ═══════════════════════════════════════════════════════════
# HTML: PÁGINA PRINCIPAL — CATÁLOGO
# ═══════════════════════════════════════════════════════════
HTML_INDEX = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>DuckDB Catalog — Orchestrator</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
:root{
  --bg:#07080f;--surface:#0d1117;--card:#111827;
  --border:#1a2332;--accent:#7c3aed;--accent2:#06b6d4;
  --pink:#ec4899;--ok:#10b981;--err:#ef4444;--warn:#f59e0b;
  --text:#f1f5f9;--muted:#4b5563;--mono:'JetBrains Mono',monospace;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:14px 28px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:200;}
.brand{font-family:var(--mono);font-size:12px;color:var(--accent2);letter-spacing:.12em;}
.brand b{color:var(--text);}
.nav{display:flex;gap:6px;}
.nav a{padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;color:var(--muted);transition:all .2s;}
.nav a:hover{color:var(--text);background:rgba(255,255,255,.05);}
.nav a.active{color:var(--accent2);background:rgba(6,182,212,.08);}
.upload-zone{margin:32px auto;max-width:1200px;padding:0 24px;}
.upload-box{border:2px dashed var(--border);border-radius:14px;padding:40px;text-align:center;cursor:pointer;transition:all .3s;background:rgba(124,58,237,.03);position:relative;}
.upload-box:hover,.upload-box.drag{border-color:var(--accent);background:rgba(124,58,237,.06);}
.upload-box input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%;}
.upload-icon{font-size:36px;margin-bottom:12px;opacity:.6;}
.upload-title{font-size:16px;font-weight:600;margin-bottom:6px;}
.upload-sub{font-size:13px;color:var(--muted);}
.upload-progress{display:none;margin-top:14px;background:rgba(255,255,255,.05);border-radius:6px;overflow:hidden;height:6px;}
.upload-progress-bar{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));width:0%;transition:width .3s;}
.section-header{max-width:1200px;margin:0 auto;padding:0 24px 16px;display:flex;align-items:center;justify-content:space-between;}
.section-title{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);}
.filter-tabs{display:flex;gap:6px;}
.filter-tab{padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid var(--border);color:var(--muted);transition:all .2s;background:none;}
.filter-tab:hover{color:var(--text);}
.filter-tab.active{background:var(--accent);border-color:var(--accent);color:#fff;}
.grid{max-width:1200px;margin:0 auto;padding:0 24px 60px;display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px;}
.db-card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;transition:transform .2s,border-color .2s;position:relative;}
.db-card:hover{transform:translateY(-2px);border-color:rgba(124,58,237,.4);}
.card-hero{position:relative;height:180px;overflow:hidden;background:linear-gradient(135deg,#1a0533 0%,#0a1628 50%,#180a2e 100%);}
.card-hero img{width:100%;height:100%;object-fit:cover;opacity:.7;}
.card-hero-gradient{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.1) 0%,rgba(0,0,0,.6) 100%);}
.card-hero-title{position:absolute;bottom:14px;left:16px;right:16px;font-family:var(--mono);font-size:22px;font-weight:700;text-shadow:0 2px 8px rgba(0,0,0,.8);letter-spacing:.06em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.card-connections{position:absolute;top:12px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,.55);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.1);padding:5px 16px;border-radius:20px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.08em;white-space:nowrap;}
.card-badge{position:absolute;top:12px;right:12px;background:rgba(0,0,0,.55);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.1);padding:4px 10px;border-radius:6px;font-family:var(--mono);font-size:10px;color:var(--accent2);}
.card-pending-overlay{position:absolute;inset:0;background:rgba(7,8,15,.75);backdrop-filter:blur(3px);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;}
.clock-icon{font-size:40px;animation:pulse 2s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:.6;transform:scale(1);}50%{opacity:1;transform:scale(1.08);}}
.pending-label{font-size:13px;font-weight:600;color:var(--warn);}
.pending-sub{font-size:11px;color:var(--muted);text-align:center;padding:0 20px;}
.card-body{padding:16px;}
.card-meta{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;}
.card-size{font-family:var(--mono);font-size:11px;color:var(--muted);}
.card-status-dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 6px var(--ok);}
.card-status-dot.pending{background:var(--warn);box-shadow:0 0 6px var(--warn);}
.card-actions{display:flex;justify-content:center;gap:8px;}
.action-btn{width:44px;height:44px;border-radius:10px;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;background:rgba(255,255,255,.06);color:var(--muted);transition:all .2s;position:relative;}
.action-btn:hover{background:rgba(255,255,255,.12);color:var(--text);transform:scale(1.08);}
.action-btn.primary{background:rgba(124,58,237,.2);color:var(--accent);}
.action-btn.primary:hover{background:rgba(124,58,237,.35);}
.action-btn[disabled]{opacity:.3;cursor:not-allowed;pointer-events:none;}
.action-tip{position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:#1e293b;border:1px solid var(--border);padding:4px 10px;border-radius:6px;font-size:10px;font-weight:600;white-space:nowrap;pointer-events:none;opacity:0;transition:opacity .15s;font-family:var(--mono);}
.action-btn:hover .action-tip{opacity:1;}
.empty-state{grid-column:1/-1;text-align:center;padding:80px 20px;color:var(--muted);}
.empty-state .empty-icon{font-size:52px;margin-bottom:16px;opacity:.4;}
.empty-state p{font-size:15px;}
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(4px);z-index:500;display:none;align-items:center;justify-content:center;padding:20px;}
.modal-backdrop.show{display:flex;}
.modal{background:var(--card);border:1px solid var(--border);border-radius:16px;width:100%;max-width:480px;box-shadow:0 24px 60px rgba(0,0,0,.6);overflow:hidden;}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:20px 24px 16px;border-bottom:1px solid var(--border);}
.modal-title{font-size:15px;font-weight:700;}
.modal-close{background:none;border:none;color:var(--muted);cursor:pointer;font-size:20px;line-height:1;padding:4px;border-radius:4px;}
.modal-close:hover{color:var(--text);}
.modal-body{padding:24px;}
.modal-footer{padding:16px 24px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end;}
.form-group{display:flex;flex-direction:column;gap:6px;margin-bottom:16px;}
label{font-size:11px;font-weight:600;letter-spacing:.05em;color:var(--muted);text-transform:uppercase;}
input,textarea,select{background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:10px 14px;font-size:13px;font-family:'Space Grotesk',sans-serif;outline:none;transition:border-color .2s;width:100%;}
input:focus,textarea:focus,select:focus{border-color:var(--accent);}
textarea{resize:vertical;min-height:70px;font-family:var(--mono);font-size:12px;}
.input-hint{font-size:11px;color:var(--muted);margin-top:4px;}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:all .2s;white-space:nowrap;}
.btn:hover{filter:brightness(1.1);}
.btn:active{transform:scale(.97);}
.btn-primary{background:var(--accent);color:#fff;}
.btn-cyan{background:var(--accent2);color:#000;}
.btn-ghost{background:rgba(255,255,255,.06);color:var(--muted);border:1px solid var(--border);}
.btn-danger{background:rgba(239,68,68,.15);color:var(--err);border:1px solid rgba(239,68,68,.2);}
.btn-sm{padding:7px 14px;font-size:12px;}
#toastContainer{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;}
.toast{display:flex;align-items:center;gap:10px;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:500;border:1px solid;min-width:240px;max-width:360px;animation:slideIn .25s ease;box-shadow:0 8px 24px rgba(0,0,0,.4);}
@keyframes slideIn{from{opacity:0;transform:translateX(20px);}to{opacity:1;transform:translateX(0);}}
.toast-ok{background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.3);color:var(--ok);}
.toast-err{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3);color:var(--err);}
.toast-info{background:rgba(6,182,212,.12);border-color:rgba(6,182,212,.3);color:var(--accent2);}
.token-display{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-family:var(--mono);font-size:12px;color:var(--ok);word-break:break-all;line-height:1.6;margin-top:12px;cursor:pointer;position:relative;transition:border-color .2s;}
.token-display:hover{border-color:var(--ok);}
.token-copy-label{position:absolute;top:8px;right:10px;font-size:10px;color:var(--muted);}
/* Caja de conexión remota */
.connect-box{background:rgba(6,182,212,.06);border:1px solid rgba(6,182,212,.2);border-radius:10px;padding:16px;margin-top:14px;}
.connect-box-title{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--accent2);margin-bottom:10px;}
.connect-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.connect-label{font-size:10px;color:var(--muted);width:52px;flex-shrink:0;font-family:var(--mono);}
.connect-val{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:7px 10px;font-family:var(--mono);font-size:11px;color:var(--text);word-break:break-all;}
.copy-btn{background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);cursor:pointer;padding:5px 8px;font-size:11px;white-space:nowrap;transition:all .2s;flex-shrink:0;}
.copy-btn:hover{color:var(--text);border-color:var(--accent2);}
.code-block{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-family:var(--mono);font-size:11px;line-height:1.7;white-space:pre;overflow-x:auto;margin-top:10px;color:var(--text);}
.struct-table{width:100%;border-collapse:collapse;margin-top:8px;}
.struct-table th{text-align:left;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:8px 12px;border-bottom:1px solid var(--border);}
.struct-table td{padding:9px 12px;border-bottom:1px solid rgba(26,35,50,.5);font-size:12px;}
.struct-table tr:hover td{background:rgba(124,58,237,.05);}
.type-pill{display:inline-block;padding:2px 8px;border-radius:4px;font-family:var(--mono);font-size:10px;font-weight:700;background:rgba(6,182,212,.12);color:var(--accent2);}
.spin{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.2);border-top-color:currentColor;border-radius:50%;animation:spin .6s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
.modal-tabs{display:flex;border-bottom:1px solid var(--border);margin-bottom:20px;}
.modal-tab{padding:10px 16px;font-size:12px;font-weight:600;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-1px;transition:all .2s;}
.modal-tab.active{color:var(--accent2);border-bottom-color:var(--accent2);}
.tab-panel{display:none;}
.tab-panel.active{display:block;}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand"><b>DUCKDB</b> CATALOG — <span>ORCHESTRATOR v5.0</span></div>
  <nav class="nav">
    <a href="/" class="active">Catálogo</a>
    <a href="/admin/tokens">Tokens</a>
    <a href="/admin/setup">Setup</a>
    <a href="/docs">API Docs</a>
  </nav>
</div>

<div class="upload-zone">
  <div class="upload-box" id="uploadBox">
    <input type="file" accept=".duckdb" id="fileInput" onchange="handleFileSelect(this)"/>
    <div class="upload-icon">🦆</div>
    <div class="upload-title">Arrastra un archivo .duckdb aquí</div>
    <div class="upload-sub">o haz clic para seleccionar · Máximo 4 GB · Se guarda en el volumen del servidor</div>
    <div class="upload-progress" id="uploadProgress">
      <div class="upload-progress-bar" id="uploadBar"></div>
    </div>
  </div>
</div>

<div class="section-header">
  <span class="section-title">Bases de Datos Registradas</span>
  <div class="filter-tabs">
    <button class="filter-tab active" onclick="filtrar(this,'all')">Todas</button>
    <button class="filter-tab" onclick="filtrar(this,'activo')">Activas</button>
    <button class="filter-tab" onclick="filtrar(this,'pendiente')">Sin configurar</button>
  </div>
</div>

<div class="grid" id="dbGrid">
  <div class="empty-state"><div class="empty-icon">⏳</div><p>Cargando catálogo…</p></div>
</div>

<div id="toastContainer"></div>

<!-- MODAL: CONFIGURAR DB -->
<div class="modal-backdrop" id="modalConfig">
  <div class="modal">
    <div class="modal-header">
      <div>
        <div class="modal-title">⚙️ Configurar base de datos</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px" id="configDbName">—</div>
      </div>
      <button class="modal-close" onclick="closeModal('modalConfig')">✕</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>Contraseña de acceso</label>
        <input type="password" id="cfgPassword" placeholder="Contraseña para generar tokens"/>
        <div class="input-hint">Se pedirá al generar tokens de acceso remoto</div>
      </div>
      <div class="form-group">
        <label>Categoría</label>
        <input id="cfgCategoria" placeholder="reniec, sunat, padron…"/>
      </div>
      <div class="form-group">
        <label>URL de imagen de portada</label>
        <input id="cfgImagen" placeholder="https://… (opcional)"/>
      </div>
      <div class="form-group">
        <label>Descripción</label>
        <textarea id="cfgDescripcion" placeholder="Describe qué contiene esta base de datos…"></textarea>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost btn-sm" onclick="closeModal('modalConfig')">Cancelar</button>
      <button class="btn btn-primary btn-sm" onclick="guardarConfig()">✔ Guardar configuración</button>
    </div>
  </div>
</div>

<!-- MODAL: GENERAR TOKEN -->
<div class="modal-backdrop" id="modalToken">
  <div class="modal" style="max-width:560px">
    <div class="modal-header">
      <div>
        <div class="modal-title">🔑 Generar token de acceso remoto</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px" id="tokenDbName">—</div>
      </div>
      <button class="modal-close" onclick="closeModal('modalToken')">✕</button>
    </div>
    <div class="modal-body">
      <div id="tokenForm">
        <div class="form-group">
          <label>Nombre del cliente / bot</label>
          <input id="tkNombre" placeholder="bot_consulta_reniec"/>
        </div>
        <div class="form-group">
          <label>Contraseña de la base de datos</label>
          <input type="password" id="tkPassword" placeholder="Para verificar que eres el dueño"/>
        </div>
        <div class="form-group">
          <label>Plan de acceso</label>
          <select id="tkPlan">
            <option value="basic">Basic — 500 consultas/día</option>
            <option value="pro">Pro — 5,000 consultas/día</option>
            <option value="enterprise">Enterprise — Sin límite</option>
          </select>
        </div>
      </div>
      <div id="tokenGenerado" style="display:none">
        <div class="connect-box">
          <div class="connect-box-title">🌐 Conexión remota lista</div>
          <div class="connect-row">
            <span class="connect-label">BASE URL</span>
            <span class="connect-val" id="connUrl">—</span>
            <button class="copy-btn" onclick="copiar('connUrl')">Copiar</button>
          </div>
          <div class="connect-row">
            <span class="connect-label">TOKEN</span>
            <span class="connect-val" id="connToken">—</span>
            <button class="copy-btn" onclick="copiar('connToken')">Copiar</button>
          </div>
        </div>
        <div style="margin-top:16px;font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin-bottom:6px">Ejemplo de uso en Python</div>
        <div class="code-block" id="pythonExample">—</div>
        <div style="font-size:11px;color:var(--warn);margin-top:10px">⚠️ Guarda el token ahora, no se puede recuperar</div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost btn-sm" onclick="closeModal('modalToken')">Cerrar</button>
      <button class="btn btn-primary btn-sm" id="btnGenerar" onclick="generarToken()">⚡ Generar token</button>
    </div>
  </div>
</div>

<!-- MODAL: INFO / ESTRUCTURA -->
<div class="modal-backdrop" id="modalEstructura">
  <div class="modal" style="max-width:620px">
    <div class="modal-header">
      <div>
        <div class="modal-title">📊 Información de la base de datos</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px" id="estructuraDbName">—</div>
      </div>
      <button class="modal-close" onclick="closeModal('modalEstructura')">✕</button>
    </div>
    <div class="modal-body" style="max-height:450px;overflow-y:auto">
      <div class="modal-tabs">
        <div class="modal-tab active" onclick="switchTab(this,'tabInfo')">Info</div>
        <div class="modal-tab" onclick="switchTab(this,'tabTokens')">Tokens activos</div>
      </div>
      <div class="tab-panel active" id="tabInfo">
        <div id="estructuraContent"><div style="text-align:center;padding:30px;color:var(--muted)">Cargando…</div></div>
      </div>
      <div class="tab-panel" id="tabTokens">
        <div id="tokensContent"><div style="text-align:center;padding:30px;color:var(--muted)">Cargando…</div></div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost btn-sm" onclick="closeModal('modalEstructura')">Cerrar</button>
    </div>
  </div>
</div>

<!-- MODAL: DESCARGAR -->
<div class="modal-backdrop" id="modalDescarga">
  <div class="modal" style="max-width:400px">
    <div class="modal-header">
      <div class="modal-title">⬇️ Descargar base de datos</div>
      <button class="modal-close" onclick="closeModal('modalDescarga')">✕</button>
    </div>
    <div class="modal-body">
      <div id="descargaDbInfo" style="font-size:13px;color:var(--muted);margin-bottom:16px">—</div>
      <div class="form-group">
        <label>Contraseña de acceso</label>
        <input type="password" id="descPassword" placeholder="Contraseña configurada para esta DB"/>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost btn-sm" onclick="closeModal('modalDescarga')">Cancelar</button>
      <button class="btn btn-cyan btn-sm" onclick="confirmarDescarga()">⬇️ Descargar</button>
    </div>
  </div>
</div>

<script>
let allDbs = [];
let currentDb = null;

function toast(msg, tipo='info') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast toast-${tipo}`;
  t.innerHTML = `<span>${{ok:'✅',err:'❌',info:'ℹ️'}[tipo]||'ℹ️'}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transform='translateX(20px)'; t.style.transition='all .3s'; setTimeout(()=>t.remove(),300); }, 3500);
}

function openModal(id){ document.getElementById(id).classList.add('show'); }
function closeModal(id){
  document.getElementById(id).classList.remove('show');
  if(id==='modalToken'){
    document.getElementById('tokenGenerado').style.display='none';
    document.getElementById('tokenForm').style.display='block';
    document.getElementById('btnGenerar').style.display='';
    document.getElementById('tkNombre').value='';
    document.getElementById('tkPassword').value='';
  }
}

function switchTab(el, panelId) {
  el.closest('.modal-tabs').querySelectorAll('.modal-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  el.closest('.modal-body').querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.getElementById(panelId).classList.add('active');
}

function copiar(elId) {
  const text = document.getElementById(elId).textContent.trim();
  navigator.clipboard.writeText(text).then(()=>toast('Copiado al portapapeles','ok'));
}

async function cargarCatalogo() {
  const r = await fetch('/api/dbs');
  allDbs = await r.json();
  renderGrid(allDbs);
}

function filtrar(btn, filtro) {
  document.querySelectorAll('.filter-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const filtered = filtro === 'all' ? allDbs
    : filtro === 'activo' ? allDbs.filter(d=>d.configurado)
    : allDbs.filter(d=>!d.configurado);
  renderGrid(filtered);
}

function renderGrid(dbs) {
  const grid = document.getElementById('dbGrid');
  if (!dbs.length) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">🦆</div><p>No hay bases de datos aún.<br/>Sube un archivo .duckdb para comenzar.</p></div>`;
    return;
  }
  grid.innerHTML = dbs.map(db => cardHTML(db)).join('');
}

function cardHTML(db) {
  const nombre = (db.nombre_db || '').replace('.duckdb','').toUpperCase();
  const cfg = db.configurado;
  const img = db.imagen_url || '';
  const conex = db.conexiones || 0;
  const tamano = db.tamano_mb ? `${db.tamano_mb} MB` : '—';
  const heroContent = img
    ? `<img src="${img}" alt="${nombre}" onerror="this.style.display='none'"/>`
    : `<div style="position:absolute;inset:0;background:linear-gradient(135deg,#1a0533,#0a1628,#180a2e)"></div>`;
  const pendingOverlay = !cfg ? `<div class="card-pending-overlay"><div class="clock-icon">⏱️</div><div class="pending-label">Sin configurar</div><div class="pending-sub">Configúrala para activarla.</div></div>` : '';
  return `<div class="db-card" data-id="${db.id}" data-cfg="${cfg}">
    <div class="card-hero">
      ${heroContent}
      <div class="card-hero-gradient"></div>
      <div class="card-connections">CONEXIONES: ${conex}</div>
      <div class="card-badge">DUCKDB</div>
      <div class="card-hero-title">${nombre}</div>
      ${pendingOverlay}
    </div>
    <div class="card-body">
      <div class="card-meta">
        <span class="card-size">${tamano} · ${db.categoria || 'sin categoría'}</span>
        <div class="card-status-dot ${cfg ? '' : 'pending'}"></div>
      </div>
      <div class="card-actions">
        <button class="action-btn primary" onclick='abrirConfig(${JSON.stringify(db)})'>
          <span>⚙️</span><span class="action-tip">Configurar DB</span>
        </button>
        <button class="action-btn ${!cfg?'':''}${!cfg?' disabled':''}" ${!cfg?'disabled':''} onclick='abrirToken(${JSON.stringify(db)})'>
          <span>🔑</span><span class="action-tip">Generar Token</span>
        </button>
        <button class="action-btn ${!cfg?'':''}${!cfg?' disabled':''}" ${!cfg?'disabled':''} onclick='abrirEstructura(${JSON.stringify(db)})'>
          <span>🔗</span><span class="action-tip">Info &amp; Tokens</span>
        </button>
        <button class="action-btn ${!cfg?'':''}${!cfg?' disabled':''}" ${!cfg?'disabled':''} onclick='abrirDescarga(${JSON.stringify(db)})'>
          <span>⬇️</span><span class="action-tip">Descargar</span>
        </button>
      </div>
    </div>
  </div>`;
}

function abrirConfig(db) {
  currentDb = db;
  document.getElementById('configDbName').textContent = db.nombre_db;
  document.getElementById('cfgPassword').value = '';
  document.getElementById('cfgCategoria').value = db.categoria || '';
  document.getElementById('cfgImagen').value = db.imagen_url || '';
  document.getElementById('cfgDescripcion').value = db.descripcion || '';
  openModal('modalConfig');
}

async function guardarConfig() {
  const pass = document.getElementById('cfgPassword').value.trim();
  if (!pass) { toast('La contraseña es obligatoria', 'err'); return; }
  const payload = {
    password_descarga: pass,
    categoria: document.getElementById('cfgCategoria').value.trim(),
    imagen_url: document.getElementById('cfgImagen').value.trim(),
    descripcion: document.getElementById('cfgDescripcion').value.trim(),
    configurado: true,
  };
  const r = await fetch(`/api/dbs/${currentDb.id}/configurar`, {
    method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
  });
  if (r.ok) { toast('Base de datos configurada ✅', 'ok'); closeModal('modalConfig'); cargarCatalogo(); }
  else toast('Error al guardar', 'err');
}

function abrirToken(db) {
  currentDb = db;
  document.getElementById('tokenDbName').textContent = db.nombre_db;
  openModal('modalToken');
}

async function generarToken() {
  const nombre = document.getElementById('tkNombre').value.trim();
  const pass   = document.getElementById('tkPassword').value.trim();
  const plan   = document.getElementById('tkPlan').value;
  if (!nombre || !pass) { toast('Nombre y contraseña requeridos', 'err'); return; }
  const r = await fetch('/api/tokens/generar', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ db_id: currentDb.id, nombre, password: pass, plan })
  });
  const data = await r.json();
  if (r.ok && data.token) {
    const baseUrl = window.location.origin;
    const dbNombre = currentDb.nombre_db;
    document.getElementById('connUrl').textContent = `${baseUrl}/api/query/${dbNombre}`;
    document.getElementById('connToken').textContent = data.token;
    document.getElementById('pythonExample').textContent =
`import requests

BASE_URL = "${baseUrl}"
DB      = "${dbNombre}"
TOKEN   = "${data.token}"

def query(sql):
    r = requests.post(
        f"{BASE_URL}/api/query/{dbNombre}",
        json={"sql": sql},
        headers={"Authorization": f"Bearer {data.token}"}
    )
    r.raise_for_status()
    return r.json()   # {"columns": [...], "rows": [...], "total": N}

# Ejemplo
resultado = query("SELECT * FROM mi_tabla LIMIT 10")
print(resultado["rows"])`;
    document.getElementById('tokenForm').style.display = 'none';
    document.getElementById('tokenGenerado').style.display = 'block';
    document.getElementById('btnGenerar').style.display = 'none';
    toast('Token generado ✅', 'ok');
  } else {
    toast(data.error || 'Error al generar token', 'err');
  }
}

async function abrirEstructura(db) {
  currentDb = db;
  document.getElementById('estructuraDbName').textContent = db.nombre_db;
  document.getElementById('estructuraContent').innerHTML = '<div style="text-align:center;padding:30px;color:var(--muted)">Cargando…</div>';
  document.getElementById('tokensContent').innerHTML = '<div style="text-align:center;padding:30px;color:var(--muted)">Cargando…</div>';
  openModal('modalEstructura');
  document.getElementById('estructuraContent').innerHTML = `
    <table class="struct-table">
      <thead><tr><th>Campo</th><th>Valor</th></tr></thead>
      <tbody>
        <tr><td>Nombre</td><td style="font-family:var(--mono)">${db.nombre_db}</td></tr>
        <tr><td>Categoría</td><td>${db.categoria || '—'}</td></tr>
        <tr><td>Tamaño en volumen</td><td>${db.tamano_mb ? db.tamano_mb + ' MB' : '—'}</td></tr>
        <tr><td>Conexiones activas</td><td>${db.conexiones || 0}</td></tr>
        <tr><td>Descripción</td><td>${db.descripcion || '—'}</td></tr>
        <tr><td>Configurado</td><td>${db.configurado ? '✅ Sí' : '⏱️ Pendiente'}</td></tr>
        <tr><td>Registrado</td><td style="font-family:var(--mono);font-size:11px">${db.creado_en ? new Date(db.creado_en).toLocaleString('es') : '—'}</td></tr>
      </tbody>
    </table>`;
  const r2 = await fetch(`/api/dbs/${db.id}/tokens`);
  const tokens = await r2.json();
  if (!tokens.length) {
    document.getElementById('tokensContent').innerHTML = '<p style="color:var(--muted);font-size:13px;padding:20px 0">No hay tokens para esta base de datos</p>';
  } else {
    document.getElementById('tokensContent').innerHTML = `
      <table class="struct-table">
        <thead><tr><th>Nombre</th><th>Plan</th><th>Estado</th><th>Creado</th></tr></thead>
        <tbody>${tokens.map(t=>`
          <tr>
            <td>${t.nombre}</td>
            <td><span class="type-pill">${t.plan}</span></td>
            <td>${t.activo ? '🟢 Activo' : '🔴 Inactivo'}</td>
            <td style="font-family:var(--mono);font-size:10px">${t.creado_en ? new Date(t.creado_en).toLocaleString('es') : '—'}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }
}

function abrirDescarga(db) {
  currentDb = db;
  document.getElementById('descargaDbInfo').textContent = `Archivo: ${db.nombre_db}`;
  document.getElementById('descPassword').value = '';
  openModal('modalDescarga');
}

async function confirmarDescarga() {
  const pass = document.getElementById('descPassword').value.trim();
  if (!pass) { toast('Ingresa la contraseña', 'err'); return; }
  const r = await fetch(`/api/dbs/${currentDb.id}/descargar`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:pass})
  });
  if (r.ok) {
    const blob = await r.blob();
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = currentDb.nombre_db; a.click();
    toast('Descarga iniciada', 'ok'); closeModal('modalDescarga');
  } else {
    const data = await r.json();
    toast(data.error || 'Contraseña incorrecta', 'err');
  }
}

// UPLOAD
const uploadBox = document.getElementById('uploadBox');
uploadBox.addEventListener('dragover', e=>{ e.preventDefault(); uploadBox.classList.add('drag'); });
uploadBox.addEventListener('dragleave', ()=>uploadBox.classList.remove('drag'));
uploadBox.addEventListener('drop', e=>{ e.preventDefault(); uploadBox.classList.remove('drag'); const f=e.dataTransfer.files[0]; if(f) subirArchivo(f); });
function handleFileSelect(input){ const f=input.files[0]; if(f) subirArchivo(f); }

async function subirArchivo(file) {
  if (!file.name.endsWith('.duckdb')) { toast('Solo se aceptan archivos .duckdb', 'err'); return; }
  const prog=document.getElementById('uploadProgress'), bar=document.getElementById('uploadBar');
  prog.style.display='block'; bar.style.width='0%';
  const formData = new FormData(); formData.append('file', file);
  let fake=0;
  const interval=setInterval(()=>{ fake=Math.min(fake+Math.random()*8,85); bar.style.width=fake+'%'; },200);
  const r = await fetch('/api/dbs/upload', { method:'POST', body:formData });
  clearInterval(interval); bar.style.width='100%';
  setTimeout(()=>{ prog.style.display='none'; bar.style.width='0%'; }, 800);
  document.getElementById('fileInput').value = '';
  if (r.ok) { toast(`${file.name} guardado en volumen ✅`, 'ok'); cargarCatalogo(); }
  else { const data=await r.json(); toast(data.error||'Error al subir archivo','err'); }
}

cargarCatalogo();
setInterval(cargarCatalogo, 30000);
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════
# HTML: ADMIN TOKENS
# ═══════════════════════════════════════════════════════════
HTML_TOKENS = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Tokens — Orchestrator</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
:root{--bg:#07080f;--surface:#0d1117;--card:#111827;--border:#1a2332;--accent:#7c3aed;--accent2:#06b6d4;--ok:#10b981;--err:#ef4444;--warn:#f59e0b;--text:#f1f5f9;--muted:#4b5563;--mono:'JetBrains Mono',monospace;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:14px 28px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:200;}
.brand{font-family:var(--mono);font-size:12px;color:var(--accent2);letter-spacing:.12em;}.brand b{color:var(--text);}
.nav a{padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;color:var(--muted);margin-left:4px;transition:all .2s;}
.nav a:hover{color:var(--text);background:rgba(255,255,255,.05);}
.nav a.active{color:var(--accent2);background:rgba(6,182,212,.08);}
.container{max-width:1100px;margin:0 auto;padding:36px 24px;}
h1{font-size:22px;font-weight:700;margin-bottom:4px;}
.subtitle{color:var(--muted);font-size:13px;margin-bottom:32px;}
table{width:100%;border-collapse:collapse;}
th{text-align:left;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:10px 14px;border-bottom:1px solid var(--border);}
td{padding:11px 14px;border-bottom:1px solid rgba(26,35,50,.6);font-size:13px;vertical-align:middle;}
tr:hover td{background:rgba(124,58,237,.04);}
.mono{font-family:var(--mono);font-size:11px;color:var(--muted);}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;}
.badge-ok{background:rgba(16,185,129,.12);color:var(--ok);}
.badge-warn{background:rgba(245,158,11,.12);color:var(--warn);}
.badge-plan{background:rgba(124,58,237,.12);color:var(--accent);}
.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;border:none;transition:all .2s;}
.btn-ghost{background:rgba(255,255,255,.05);color:var(--muted);border:1px solid var(--border);}
.btn-danger{background:rgba(239,68,68,.1);color:var(--err);border:1px solid rgba(239,68,68,.2);}
.btn:hover{filter:brightness(1.15);}
.empty{color:var(--muted);font-size:13px;padding:40px;text-align:center;}
#toastContainer{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;}
.toast{display:flex;align-items:center;gap:10px;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:500;border:1px solid;min-width:220px;animation:slideIn .25s ease;}
@keyframes slideIn{from{opacity:0;transform:translateX(20px);}to{opacity:1;transform:translateX(0);}}
.toast-ok{background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.3);color:var(--ok);}
.toast-err{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3);color:var(--err);}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand"><b>DUCKDB</b> CATALOG — <span>ORCHESTRATOR v5.0</span></div>
  <nav class="nav">
    <a href="/">Catálogo</a>
    <a href="/admin/tokens" class="active">Tokens</a>
    <a href="/admin/setup">Setup</a>
    <a href="/docs">API Docs</a>
  </nav>
</div>
<div class="container">
  <h1>Tokens de Acceso Remoto</h1>
  <p class="subtitle">Todos los tokens para consulta remota de bases de datos DuckDB</p>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <span style="font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)">Tokens registrados</span>
    <button class="btn btn-ghost" onclick="cargar()">⟳ Actualizar</button>
  </div>
  <div id="tablaContainer"><p class="empty">Cargando…</p></div>
</div>
<div id="toastContainer"></div>
<script>
function toast(msg,tipo='ok'){
  const c=document.getElementById('toastContainer');
  const t=document.createElement('div'); t.className=`toast toast-${tipo}`;
  t.innerHTML=`<span>${tipo==='ok'?'✅':'❌'}</span><span>${msg}</span>`;
  c.appendChild(t); setTimeout(()=>{t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(()=>t.remove(),300);},3000);
}
async function cargar(){
  const r=await fetch('/api/tokens'); const data=await r.json();
  const cont=document.getElementById('tablaContainer');
  if(!data.length){cont.innerHTML='<p class="empty">Sin tokens registrados</p>';return;}
  cont.innerHTML=`<table>
    <thead><tr><th>Nombre</th><th>Base de Datos</th><th>Plan</th><th>Estado</th><th>Creado</th><th></th></tr></thead>
    <tbody>${data.map(t=>`<tr>
      <td>${t.nombre}</td>
      <td class="mono">${t.db_nombre||'—'}</td>
      <td><span class="badge badge-plan">${t.plan}</span></td>
      <td>${t.activo?'<span class="badge badge-ok">Activo</span>':'<span class="badge badge-warn">Inactivo</span>'}</td>
      <td class="mono">${t.creado_en?new Date(t.creado_en).toLocaleString('es'):'—'}</td>
      <td><button class="btn btn-danger" onclick="revocar(${t.id})">Revocar</button></td>
    </tr>`).join('')}</tbody></table>`;
}
async function revocar(id){
  if(!confirm('¿Revocar este token?'))return;
  const r=await fetch(`/api/tokens/${id}/revocar`,{method:'PATCH'});
  if(r.ok){toast('Token revocado');cargar();}else toast('Error','err');
}
cargar();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════
# HTML: SETUP
# ═══════════════════════════════════════════════════════════
HTML_SETUP = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/><title>Setup — Orchestrator</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
:root{--bg:#07080f;--surface:#0d1117;--card:#111827;--border:#1a2332;--accent:#7c3aed;--accent2:#06b6d4;--ok:#10b981;--err:#ef4444;--text:#f1f5f9;--muted:#4b5563;--mono:'JetBrains Mono',monospace;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:14px 28px;background:var(--surface);border-bottom:1px solid var(--border);}
.brand{font-family:var(--mono);font-size:12px;color:var(--accent2);letter-spacing:.12em;}.brand b{color:var(--text);}
.nav a{padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;color:var(--muted);margin-left:4px;}
.nav a:hover{color:var(--text);}.nav a.active{color:var(--accent2);}
.container{max-width:700px;margin:0 auto;padding:48px 24px;}
h1{font-size:22px;font-weight:700;margin-bottom:6px;}
.subtitle{color:var(--muted);font-size:13px;margin-bottom:32px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:16px;}
.card-title{font-size:14px;font-weight:700;margin-bottom:6px;}
.card-desc{font-size:12px;color:var(--muted);margin-bottom:16px;line-height:1.6;}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:all .2s;}
.btn-primary{background:var(--accent);color:#fff;}.btn-ghost{background:rgba(255,255,255,.05);color:var(--muted);border:1px solid var(--border);}
.btn:hover{filter:brightness(1.1);}
.result{margin-top:14px;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-family:var(--mono);font-size:12px;line-height:1.7;white-space:pre-wrap;display:none;max-height:200px;overflow-y:auto;}
.result.show{display:block;}.ok-line{color:var(--ok);}.err-line{color:var(--err);}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand"><b>DUCKDB</b> CATALOG — <span>ORCHESTRATOR v5.0</span></div>
  <nav class="nav">
    <a href="/">Catálogo</a><a href="/admin/tokens">Tokens</a>
    <a href="/admin/setup" class="active">Setup</a><a href="/docs">API Docs</a>
  </nav>
</div>
<div class="container">
  <h1>Setup del Sistema</h1>
  <p class="subtitle">Inicializa las tablas en Supabase (solo catálogo y tokens) y verifica el volumen de almacenamiento</p>
  <div class="card">
    <div class="card-title">1. Crear tablas en Supabase</div>
    <div class="card-desc">Crea <code>catalog_dbs</code> y <code>catalog_tokens</code>. Los archivos .duckdb viven en el volumen Docker, NO en Supabase.</div>
    <button class="btn btn-primary" onclick="crearTablas()">▶ Ejecutar migración</button>
    <div class="result" id="rTablas"></div>
  </div>
  <div class="card">
    <div class="card-title">2. Verificar sistema</div>
    <div class="card-desc">Chequea Supabase, las tablas y el volumen de storage del servidor.</div>
    <button class="btn btn-ghost" onclick="verificar()">⟳ Verificar</button>
    <div class="result" id="rVerify"></div>
  </div>
</div>
<script>
function mostrar(id, lineas){
  const el=document.getElementById(id);
  el.innerHTML=lineas.map(l=>`<span class="${l.ok?'ok-line':'err-line'}">${l.ok?'✅':'❌'} ${l.msg}</span>\n`).join('');
  el.classList.add('show');
}
async function crearTablas(){
  const r=await fetch('/api/setup/init',{method:'POST'});
  const data=await r.json(); mostrar('rTablas',data.resultados);
}
async function verificar(){
  const r=await fetch('/api/check'); const data=await r.json();
  mostrar('rVerify',data.checks.map(c=>({ok:c.ok,msg:`${c.nombre}: ${c.detalle}`})));
}
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════
# RUTAS HTML
# ═══════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def index(): return HTML_INDEX

@app.get("/admin/tokens", response_class=HTMLResponse)
async def admin_tokens(): return HTML_TOKENS

@app.get("/admin/setup", response_class=HTMLResponse)
async def admin_setup(): return HTML_SETUP


# ═══════════════════════════════════════════════════════════
# API: BASES DE DATOS
# ═══════════════════════════════════════════════════════════
@app.get("/api/dbs")
async def listar_dbs():
    dbs = sb_get("catalog_dbs", "?select=*&order=creado_en.desc")
    if not isinstance(dbs, list):
        dbs = []
    for db in dbs:
        tokens = sb_get("catalog_tokens", f"?select=id&db_id=eq.{db['id']}&activo=eq.true")
        db["conexiones"] = len(tokens) if isinstance(tokens, list) else 0
        path = os.path.join(STORAGE_DIR, db.get("nombre_db", ""))
        if os.path.exists(path):
            db["tamano_mb"] = round(os.path.getsize(path) / 1024 / 1024, 2)
    return dbs


@app.post("/api/dbs/upload")
async def upload_db(file: UploadFile = File(...)):
    """Guarda el archivo .duckdb en el volumen del servidor y registra metadata en Supabase."""
    if not file.filename.endswith(".duckdb"):
        raise HTTPException(400, "Solo archivos .duckdb")
    dest = os.path.join(STORAGE_DIR, file.filename)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    # Registrar metadata en Supabase (solo nombre + estado)
    existing = sb_get("catalog_dbs", f"?nombre_db=eq.{file.filename}")
    if not isinstance(existing, list) or len(existing) == 0:
        status, data = sb_post("catalog_dbs", {
            "nombre_db": file.filename,
            "configurado": False,
            "conexiones": 0,
        })
        if status not in (200, 201):
            return JSONResponse(
                {"error": "Archivo guardado en volumen pero no pudo registrarse en Supabase", "detail": str(data)},
                status_code=500
            )
    return {"ok": True, "nombre": file.filename, "bytes": len(content), "ruta_volumen": dest}


@app.patch("/api/dbs/{db_id}/configurar")
async def configurar_db(db_id: int, request: Request):
    payload = await request.json()
    status, data = sb_patch("catalog_dbs", f"?id=eq.{db_id}", payload)
    if status in (200, 204):
        return {"ok": True}
    return JSONResponse({"error": str(data)}, status_code=400)


@app.get("/api/dbs/{db_id}/tokens")
async def tokens_de_db(db_id: int):
    t = sb_get("catalog_tokens", f"?db_id=eq.{db_id}&select=*&order=creado_en.desc")
    return t if isinstance(t, list) else []


@app.post("/api/dbs/{db_id}/descargar")
async def descargar_db(db_id: int, request: Request):
    body = await request.json()
    password = body.get("password", "")
    dbs = sb_get("catalog_dbs", f"?id=eq.{db_id}&select=*")
    if not isinstance(dbs, list) or not dbs:
        raise HTTPException(404, "DB no encontrada")
    db = dbs[0]
    if db.get("password_descarga", "") != password:
        return JSONResponse({"error": "Contraseña incorrecta"}, status_code=403)
    path = os.path.join(STORAGE_DIR, db["nombre_db"])
    if not os.path.exists(path):
        return JSONResponse({"error": "Archivo no encontrado en el volumen"}, status_code=404)
    return FileResponse(path, filename=db["nombre_db"], media_type="application/octet-stream")


# ═══════════════════════════════════════════════════════════
# API: QUERY REMOTA DUCKDB  ← núcleo del sistema
# ═══════════════════════════════════════════════════════════
@app.post("/api/query/{db_nombre}")
async def query_remota(db_nombre: str, request: Request):
    """
    Ejecuta SQL sobre un archivo DuckDB que vive en el volumen del servidor.
    
    Headers requeridos:
        Authorization: Bearer <token>

    Body JSON:
        { "sql": "SELECT * FROM tabla LIMIT 10" }

    Respuesta:
        { "columns": [...], "rows": [[...], ...], "total": N }

    Uso desde Python:
        import requests
        r = requests.post(
            "http://mi-servidor:8000/api/query/mi_base.duckdb",
            json={"sql": "SELECT count(*) FROM registros"},
            headers={"Authorization": "Bearer tk_xxxxx"}
        )
        print(r.json())
    """
    # Autenticación por token en header
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Se requiere Authorization: Bearer <token>")
    token_val = auth.removeprefix("Bearer ").strip()
    tk, db_row = resolver_token(token_val)

    # Verificar que el token corresponde a esta DB
    if db_row.get("nombre_db") != db_nombre:
        raise HTTPException(403, "Este token no pertenece a esta base de datos")

    body = await request.json()
    sql = body.get("sql", "").strip()
    if not sql:
        raise HTTPException(400, "Campo 'sql' requerido")

    # Bloquear escrituras (solo lectura remota)
    sql_upper = sql.upper().lstrip()
    ESCRITURAS = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "COPY", "ATTACH")
    if any(sql_upper.startswith(w) for w in ESCRITURAS):
        raise HTTPException(403, "Solo se permiten consultas SELECT en el acceso remoto")

    path = os.path.join(STORAGE_DIR, db_nombre)
    if not os.path.exists(path):
        raise HTTPException(404, f"Archivo '{db_nombre}' no encontrado en el volumen del servidor")

    try:
        con = duckdb.connect(path, read_only=True)
        rel = con.execute(sql)
        columns = [desc[0] for desc in rel.description]
        rows = rel.fetchall()
        con.close()
        return {
            "ok": True,
            "columns": columns,
            "rows": [list(r) for r in rows],
            "total": len(rows),
            "db": db_nombre,
        }
    except duckdb.Error as e:
        raise HTTPException(400, f"Error DuckDB: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Error interno: {str(e)}")


@app.get("/api/connect/{db_nombre}")
async def info_conexion(db_nombre: str, request: Request):
    """
    Devuelve la URL de query y el token para conectarse a una DB.
    Requiere Authorization: Bearer <token>
    
    Uso rápido en Python para obtener los datos de conexión:
        r = requests.get(
            "http://mi-servidor:8000/api/connect/mi_base.duckdb",
            headers={"Authorization": "Bearer tk_xxxxx"}
        )
        info = r.json()
        # info["query_url"]  → URL donde hacer las queries
        # info["token"]      → el mismo token para reusar
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Se requiere Authorization: Bearer <token>")
    token_val = auth.removeprefix("Bearer ").strip()
    tk, db_row = resolver_token(token_val)

    if db_row.get("nombre_db") != db_nombre:
        raise HTTPException(403, "Token no pertenece a esta base de datos")

    base = str(request.base_url).rstrip("/")
    return {
        "ok": True,
        "db": db_nombre,
        "query_url": f"{base}/api/query/{db_nombre}",
        "token": token_val,
        "plan": tk.get("plan"),
        "limite_diario": tk.get("limite_diario"),
        "python_example": (
            f'import requests\n'
            f'\n'
            f'def query(sql):\n'
            f'    r = requests.post(\n'
            f'        "{base}/api/query/{db_nombre}",\n'
            f'        json={{"sql": sql}},\n'
            f'        headers={{"Authorization": "Bearer {token_val}"}}\n'
            f'    )\n'
            f'    r.raise_for_status()\n'
            f'    return r.json()\n'
            f'\n'
            f'resultado = query("SELECT * FROM mi_tabla LIMIT 10")\n'
            f'print(resultado["rows"])'
        )
    }


# ═══════════════════════════════════════════════════════════
# API: TOKENS
# ═══════════════════════════════════════════════════════════
@app.get("/api/tokens")
async def listar_tokens():
    tokens = sb_get("catalog_tokens", "?select=*,catalog_dbs(nombre_db)&order=creado_en.desc")
    if not isinstance(tokens, list):
        return []
    for t in tokens:
        if isinstance(t.get("catalog_dbs"), dict):
            t["db_nombre"] = t["catalog_dbs"].get("nombre_db", "")
            del t["catalog_dbs"]
    return tokens


@app.post("/api/tokens/generar")
async def generar_token(request: Request):
    body = await request.json()
    db_id    = body.get("db_id")
    nombre   = body.get("nombre", "").strip()
    password = body.get("password", "").strip()
    plan     = body.get("plan", "basic")
    if not db_id or not nombre or not password:
        return JSONResponse({"error": "Faltan campos requeridos"}, status_code=400)
    dbs = sb_get("catalog_dbs", f"?id=eq.{db_id}&select=password_descarga,nombre_db")
    if not isinstance(dbs, list) or not dbs:
        return JSONResponse({"error": "DB no encontrada"}, status_code=404)
    if dbs[0].get("password_descarga", "") != password:
        return JSONResponse({"error": "Contraseña incorrecta"}, status_code=403)
    token_val = "tk_" + secrets.token_hex(24)
    limites = {"basic": 500, "pro": 5000, "enterprise": 999999}
    status, data = sb_post("catalog_tokens", {
        "db_id": db_id,
        "nombre": nombre,
        "token": token_val,
        "plan": plan,
        "limite_diario": limites.get(plan, 500),
        "activo": True,
    })
    if status in (200, 201):
        return {"ok": True, "token": token_val, "db_nombre": dbs[0].get("nombre_db")}
    return JSONResponse({"error": str(data)}, status_code=500)


@app.patch("/api/tokens/{token_id}/revocar")
async def revocar_token(token_id: int):
    status, data = sb_patch("catalog_tokens", f"?id=eq.{token_id}", {"activo": False})
    return {"ok": status in (200, 204)}


# ═══════════════════════════════════════════════════════════
# API: SETUP & HEALTH
# ═══════════════════════════════════════════════════════════
MIGRACIONES = {
    "catalog_dbs": """
        CREATE TABLE IF NOT EXISTS public.catalog_dbs (
            id                BIGSERIAL PRIMARY KEY,
            nombre_db         TEXT NOT NULL,
            password_descarga TEXT,
            categoria         TEXT,
            imagen_url        TEXT,
            descripcion       TEXT,
            configurado       BOOLEAN DEFAULT FALSE,
            conexiones        INTEGER DEFAULT 0,
            creado_en         TIMESTAMPTZ DEFAULT NOW()
        );
    """,
    "catalog_tokens": """
        CREATE TABLE IF NOT EXISTS public.catalog_tokens (
            id            BIGSERIAL PRIMARY KEY,
            db_id         BIGINT REFERENCES public.catalog_dbs(id) ON DELETE CASCADE,
            nombre        TEXT NOT NULL,
            token         TEXT UNIQUE NOT NULL,
            plan          TEXT DEFAULT 'basic',
            limite_diario INTEGER DEFAULT 500,
            activo        BOOLEAN DEFAULT TRUE,
            creado_en     TIMESTAMPTZ DEFAULT NOW()
        );
    """,
}


@app.post("/api/setup/init")
async def setup_init():
    resultados = []
    for nombre, sql in MIGRACIONES.items():
        status, _ = ejecutar_sql(sql.strip())
        ok = status in (200, 201, 204)
        resultados.append({"tabla": nombre, "ok": ok, "msg": f"Tabla '{nombre}': HTTP {status}", "status": status})
    return {"resultados": resultados}


@app.get("/api/check")
async def check():
    checks = []

    # Supabase
    def ping(nombre, url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=6)
            checks.append({"nombre": nombre, "ok": r.status_code < 400, "detalle": f"HTTP {r.status_code}"})
        except Exception as e:
            checks.append({"nombre": nombre, "ok": False, "detalle": str(e)[:60]})

    ping("Supabase REST",   f"{SUPABASE_URL}/rest/v1/")
    ping("catalog_dbs",     f"{SUPABASE_URL}/rest/v1/catalog_dbs?select=id&limit=1")
    ping("catalog_tokens",  f"{SUPABASE_URL}/rest/v1/catalog_tokens?select=id&limit=1")

    # Volumen de almacenamiento
    volumen_ok = os.path.isdir(STORAGE_DIR) and os.access(STORAGE_DIR, os.W_OK)
    archivos = [f for f in os.listdir(STORAGE_DIR) if f.endswith(".duckdb")] if volumen_ok else []
    checks.append({
        "nombre": "Volumen storage",
        "ok": volumen_ok,
        "detalle": f"{len(archivos)} archivo(s) .duckdb en {STORAGE_DIR}" if volumen_ok else "No accesible"
    })

    return {"checks": checks}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
