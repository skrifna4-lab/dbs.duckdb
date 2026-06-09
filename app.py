"""
Orchestrator Core API SaaS — Dashboard de Control
Sistema: DuckDB + Supabase Hybrid Streamer v3.5.0
"""

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
import requests
import json

app = FastAPI(title="Orchestrator Core API", version="3.5.0")

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN CENTRAL
# ──────────────────────────────────────────────────────────────
SUPABASE_URL     = "http://skrifna-supabase-473c9f-192-129-183-187.sslip.io"
DUCKDB_API_URL   = "http://skrifna-duckdb-zokthr-c57021-192-129-183-187.sslip.io"
SERVICE_ROLE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpYXQiOjE3ODEwMTQzOTksImV4cCI6MTg5MzQ1NjAwMCwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlzcyI6InN1cGFiYXNlIn0"
    ".L4hICENRSDn6FRSX1YDj0dxYrnmIjEPsieqvCW8VMj4"
)

HEADERS = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "apiKey": SERVICE_ROLE_KEY,
    "Content-Type": "application/json",
}


# ──────────────────────────────────────────────────────────────
# HTML: PÁGINA PRINCIPAL — DASHBOARD DE ESTADO
# ──────────────────────────────────────────────────────────────
HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Orchestrator Core — Panel de Control</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

  :root {
    --bg:      #0a0e1a;
    --surface: #111827;
    --border:  #1e2d45;
    --accent:  #3b82f6;
    --accent2: #06b6d4;
    --ok:      #10b981;
    --warn:    #f59e0b;
    --err:     #ef4444;
    --text:    #e2e8f0;
    --muted:   #64748b;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Space Grotesk', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }

  /* TOPBAR */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 32px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .topbar-brand {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--accent);
    letter-spacing: 0.08em;
  }
  .topbar-brand span { color: var(--muted); }
  .topbar-nav a {
    color: var(--muted);
    text-decoration: none;
    font-size: 13px;
    margin-left: 24px;
    transition: color .2s;
  }
  .topbar-nav a:hover { color: var(--text); }
  .topbar-nav a.active { color: var(--accent); }

  /* LAYOUT */
  .container { max-width: 1100px; margin: 0 auto; padding: 40px 24px; }
  h1 { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
  .subtitle { color: var(--muted); font-size: 14px; margin-bottom: 40px; }

  /* STATUS GRID */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 16px; margin-bottom: 40px; }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 22px 20px;
  }
  .card-label { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }
  .card-value { font-family: 'JetBrains Mono', monospace; font-size: 22px; font-weight: 700; }
  .card-value.ok   { color: var(--ok); }
  .card-value.warn { color: var(--warn); }
  .card-value.err  { color: var(--err); }

  /* SECTION */
  .section-title {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }

  /* CHECKS TABLE */
  .checks { width: 100%; border-collapse: collapse; margin-bottom: 40px; }
  .checks th {
    text-align: left;
    font-size: 11px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 10px 14px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .checks td { padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 14px; }
  .checks tr:hover td { background: rgba(59,130,246,.04); }
  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .04em;
  }
  .badge-ok   { background: rgba(16,185,129,.15); color: var(--ok); }
  .badge-err  { background: rgba(239,68,68,.15);  color: var(--err); }
  .badge-pend { background: rgba(245,158,11,.15); color: var(--warn); }

  /* BUTTON */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 20px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: opacity .2s;
  }
  .btn:hover { opacity: .85; }
  .btn-primary { background: var(--accent);  color: #fff; }
  .btn-cyan    { background: var(--accent2); color: #000; }
  .btn-ghost   {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
  }

  .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 40px; }

  /* LOG BOX */
  .log-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.7;
    min-height: 100px;
    max-height: 280px;
    overflow-y: auto;
    white-space: pre-wrap;
  }
  .log-ok   { color: var(--ok); }
  .log-err  { color: var(--err); }
  .log-info { color: var(--accent); }

  /* SPINNER */
  .spin {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin .6s linear infinite;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-brand">ORCHESTRATOR <span>CORE API</span> — v3.5.0</div>
  <nav class="topbar-nav">
    <a href="/" class="active">Dashboard</a>
    <a href="/tablas">Tablas</a>
    <a href="/tokens">Tokens</a>
    <a href="/databases">Databases</a>
    <a href="/docs">API Docs</a>
  </nav>
</div>

<div class="container">
  <h1>Panel de Control del Sistema</h1>
  <p class="subtitle">Estado en tiempo real · Supabase + DuckDB Hybrid Streamer</p>

  <div class="grid" id="statsGrid">
    <div class="card"><div class="card-label">Supabase API</div><div class="card-value warn" id="statSupabase">verificando…</div></div>
    <div class="card"><div class="card-label">DuckDB API</div><div class="card-value warn" id="statDuckdb">verificando…</div></div>
    <div class="card"><div class="card-label">Tabla metadata_dbs</div><div class="card-value warn" id="statDbs">verificando…</div></div>
    <div class="card"><div class="card-label">Tabla metadata_tokens</div><div class="card-value warn" id="statTokens">verificando…</div></div>
  </div>

  <p class="section-title">Chequeos de Infraestructura</p>
  <table class="checks" id="checksTable">
    <thead><tr><th>Servicio</th><th>Endpoint</th><th>Estado</th><th>Detalles</th></tr></thead>
    <tbody id="checksBody">
      <tr><td colspan="4" style="color:var(--muted);padding:20px 14px">Ejecutando chequeos…</td></tr>
    </tbody>
  </table>

  <p class="section-title">Acciones Rápidas</p>
  <div class="actions">
    <button class="btn btn-primary" onclick="runChecks()">⟳ Re-chequear sistema</button>
    <button class="btn btn-cyan"    onclick="crearTablas()">+ Crear tablas base</button>
    <button class="btn btn-ghost"   onclick="window.location='/tablas'">Ver tablas →</button>
  </div>

  <p class="section-title">Log de Operaciones</p>
  <div class="log-box" id="logBox">Esperando acciones del operador…\n</div>
</div>

<script>
const log = (msg, cls='') => {
  const box = document.getElementById('logBox');
  const line = document.createElement('span');
  if (cls) line.className = cls;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}\n`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
};

async function runChecks() {
  document.getElementById('checksBody').innerHTML =
    '<tr><td colspan="4" style="color:var(--muted);padding:20px 14px">Ejecutando…</td></tr>';
  log('Iniciando chequeo de infraestructura…', 'log-info');

  const res = await fetch('/api/check');
  const data = await res.json();

  let html = '';
  data.checks.forEach(c => {
    const badge = c.ok
      ? '<span class="badge badge-ok">OK</span>'
      : '<span class="badge badge-err">ERROR</span>';
    html += `<tr>
      <td>${c.nombre}</td>
      <td style="font-family:monospace;font-size:12px;color:var(--muted)">${c.endpoint}</td>
      <td>${badge}</td>
      <td style="font-size:13px;color:var(--muted)">${c.detalle}</td>
    </tr>`;
    log(`${c.nombre}: ${c.detalle}`, c.ok ? 'log-ok' : 'log-err');
  });
  document.getElementById('checksBody').innerHTML = html;

  // Update stat cards
  const map = {
    'Supabase REST': 'statSupabase',
    'DuckDB API':    'statDuckdb',
    'metadata_dbs':  'statDbs',
    'metadata_tokens':'statTokens',
  };
  data.checks.forEach(c => {
    const id = map[c.nombre];
    if (!id) return;
    const el = document.getElementById(id);
    el.textContent = c.ok ? 'ONLINE' : 'ERROR';
    el.className = 'card-value ' + (c.ok ? 'ok' : 'err');
  });
}

async function crearTablas() {
  log('Enviando comando para crear tablas base…', 'log-info');
  const res  = await fetch('/api/crear-tablas', { method: 'POST' });
  const data = await res.json();
  data.resultados.forEach(r => log(r.msg, r.ok ? 'log-ok' : 'log-err'));
}

// Auto-run on load
window.onload = runChecks;
</script>
</body>
</html>
"""

# ──────────────────────────────────────────────────────────────
# HTML: GESTIÓN DE TABLAS
# ──────────────────────────────────────────────────────────────
HTML_TABLAS = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Orchestrator — Tablas</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
  :root{--bg:#0a0e1a;--surface:#111827;--border:#1e2d45;--accent:#3b82f6;--accent2:#06b6d4;--ok:#10b981;--err:#ef4444;--warn:#f59e0b;--text:#e2e8f0;--muted:#64748b;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
  .topbar{display:flex;align-items:center;justify-content:space-between;padding:18px 32px;border-bottom:1px solid var(--border);background:var(--surface);position:sticky;top:0;z-index:100;}
  .topbar-brand{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent);letter-spacing:.08em;}
  .topbar-brand span{color:var(--muted);}
  .topbar-nav a{color:var(--muted);text-decoration:none;font-size:13px;margin-left:24px;}
  .topbar-nav a:hover{color:var(--text);}
  .topbar-nav a.active{color:var(--accent);}
  .container{max-width:1100px;margin:0 auto;padding:40px 24px;}
  h1{font-size:26px;font-weight:700;margin-bottom:6px;}
  .subtitle{color:var(--muted);font-size:14px;margin-bottom:40px;}
  .section-title{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--border);}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:20px;}
  .form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
  .form-group{display:flex;flex-direction:column;gap:6px;}
  label{font-size:12px;color:var(--muted);letter-spacing:.04em;}
  input,textarea,select{
    background:var(--bg);border:1px solid var(--border);border-radius:6px;
    color:var(--text);padding:10px 12px;font-size:13px;font-family:inherit;
    outline:none;transition:border-color .2s;
  }
  input:focus,textarea:focus{border-color:var(--accent);}
  textarea{resize:vertical;min-height:80px;font-family:'JetBrains Mono',monospace;font-size:12px;}
  .btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:opacity .2s;}
  .btn:hover{opacity:.85;}
  .btn-primary{background:var(--accent);color:#fff;}
  .btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border);}
  .btn-danger{background:rgba(239,68,68,.15);color:var(--err);border:1px solid rgba(239,68,68,.3);}
  .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;}
  .badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}
  .badge-ok{background:rgba(16,185,129,.15);color:var(--ok);}
  .badge-err{background:rgba(239,68,68,.15);color:var(--err);}
  .result-box{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--muted);margin-top:14px;white-space:pre-wrap;max-height:200px;overflow-y:auto;display:none;}
  .result-box.show{display:block;}
  table{width:100%;border-collapse:collapse;margin-top:14px;}
  th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:10px 14px;background:var(--surface);border-bottom:1px solid var(--border);}
  td{padding:12px 14px;border-bottom:1px solid var(--border);font-size:13px;}
  tr:hover td{background:rgba(59,130,246,.04);}
  .mono{font-family:'JetBrains Mono',monospace;font-size:12px;}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-brand">ORCHESTRATOR <span>CORE API</span> — v3.5.0</div>
  <nav class="topbar-nav">
    <a href="/">Dashboard</a>
    <a href="/tablas" class="active">Tablas</a>
    <a href="/tokens">Tokens</a>
    <a href="/databases">Databases</a>
    <a href="/docs">API Docs</a>
  </nav>
</div>

<div class="container">
  <h1>Gestión de Tablas</h1>
  <p class="subtitle">Crear tablas en Supabase y ejecutar SQL vía RPC tunnel</p>

  <!-- CREAR TABLA CON SQL CUSTOM -->
  <p class="section-title">Ejecutar SQL Personalizado (vía RPC ejecutar_sql_remoto)</p>
  <div class="card">
    <div class="form-group">
      <label>QUERY SQL</label>
      <textarea id="sqlQuery" placeholder="CREATE TABLE IF NOT EXISTS public.mi_tabla (&#10;  id BIGSERIAL PRIMARY KEY,&#10;  nombre TEXT NOT NULL,&#10;  creado_en TIMESTAMPTZ DEFAULT NOW()&#10;);"></textarea>
    </div>
    <div class="actions">
      <button class="btn btn-primary" onclick="ejecutarSQL()">▶ Ejecutar SQL</button>
      <button class="btn btn-ghost" onclick="cargarEjemplo()">Cargar ejemplo</button>
    </div>
    <div class="result-box" id="sqlResult"></div>
  </div>

  <!-- VER DATOS DE TABLA -->
  <p class="section-title">Leer Tabla (GET PostgREST)</p>
  <div class="card">
    <div class="form-row">
      <div class="form-group">
        <label>NOMBRE DE TABLA</label>
        <input id="tablaLeer" placeholder="metadata_dbs" value="metadata_dbs"/>
      </div>
      <div class="form-group">
        <label>FILTRO (opcional)</label>
        <input id="tablaFiltro" placeholder="?select=*&limit=20" value="?select=*&limit=20"/>
      </div>
    </div>
    <div class="actions">
      <button class="btn btn-primary" onclick="leerTabla()">Leer tabla</button>
    </div>
    <div id="tablaResultContainer">
      <div class="result-box" id="tablaResult"></div>
    </div>
  </div>

  <!-- INSERTAR FILA -->
  <p class="section-title">Insertar Fila (POST PostgREST)</p>
  <div class="card">
    <div class="form-row">
      <div class="form-group">
        <label>TABLA DESTINO</label>
        <input id="insertTabla" placeholder="metadata_dbs" value="metadata_dbs"/>
      </div>
    </div>
    <div class="form-group" style="margin-bottom:12px">
      <label>PAYLOAD JSON</label>
      <textarea id="insertPayload">{"nombre_db": "prueba.duckdb", "categoria": "test", "activo": true}</textarea>
    </div>
    <div class="actions">
      <button class="btn btn-primary" onclick="insertarFila()">+ Insertar fila</button>
    </div>
    <div class="result-box" id="insertResult"></div>
  </div>
</div>

<script>
function mostrar(id, data, ok=true) {
  const el = document.getElementById(id);
  el.textContent = JSON.stringify(data, null, 2);
  el.style.color = ok ? 'var(--ok)' : 'var(--err)';
  el.classList.add('show');
}

function cargarEjemplo() {
  document.getElementById('sqlQuery').value =
    "CREATE TABLE IF NOT EXISTS public.proyectos (\\n  id BIGSERIAL PRIMARY KEY,\\n  nombre TEXT NOT NULL,\\n  descripcion TEXT,\\n  creado_en TIMESTAMPTZ DEFAULT NOW()\\n);";
}

async function ejecutarSQL() {
  const query = document.getElementById('sqlQuery').value.trim();
  if (!query) return alert('Escribe una query SQL');
  const res  = await fetch('/api/sql', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({query})
  });
  const data = await res.json();
  mostrar('sqlResult', data, res.ok);
}

async function leerTabla() {
  const tabla   = document.getElementById('tablaLeer').value.trim();
  const filtro  = document.getElementById('tablaFiltro').value.trim();
  const res     = await fetch(`/api/tabla/${tabla}${filtro}`);
  const data    = await res.json();
  mostrar('tablaResult', data, res.ok);
}

async function insertarFila() {
  const tabla   = document.getElementById('insertTabla').value.trim();
  let payload;
  try { payload = JSON.parse(document.getElementById('insertPayload').value); }
  catch { return alert('JSON inválido en el payload'); }

  const res  = await fetch(`/api/tabla/${tabla}`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  mostrar('insertResult', data, res.ok);
}
</script>
</body>
</html>
"""

# ──────────────────────────────────────────────────────────────
# HTML: GESTIÓN DE TOKENS
# ──────────────────────────────────────────────────────────────
HTML_TOKENS = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Orchestrator — Tokens</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
  :root{--bg:#0a0e1a;--surface:#111827;--border:#1e2d45;--accent:#3b82f6;--ok:#10b981;--err:#ef4444;--warn:#f59e0b;--text:#e2e8f0;--muted:#64748b;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
  .topbar{display:flex;align-items:center;justify-content:space-between;padding:18px 32px;border-bottom:1px solid var(--border);background:var(--surface);position:sticky;top:0;z-index:100;}
  .topbar-brand{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent);letter-spacing:.08em;}
  .topbar-brand span{color:var(--muted);}
  .topbar-nav a{color:var(--muted);text-decoration:none;font-size:13px;margin-left:24px;}
  .topbar-nav a:hover{color:var(--text);}
  .topbar-nav a.active{color:var(--accent);}
  .container{max-width:1100px;margin:0 auto;padding:40px 24px;}
  h1{font-size:26px;font-weight:700;margin-bottom:6px;}
  .subtitle{color:var(--muted);font-size:14px;margin-bottom:40px;}
  .section-title{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--border);}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:20px;}
  .form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
  .form-group{display:flex;flex-direction:column;gap:6px;}
  label{font-size:12px;color:var(--muted);letter-spacing:.04em;}
  input,select{background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:10px 12px;font-size:13px;font-family:inherit;outline:none;transition:border-color .2s;}
  input:focus{border-color:var(--accent);}
  .btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:opacity .2s;}
  .btn:hover{opacity:.85;}
  .btn-primary{background:var(--accent);color:#fff;}
  .btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border);}
  .actions{display:flex;gap:10px;margin-top:14px;}
  table{width:100%;border-collapse:collapse;}
  th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:10px 14px;border-bottom:1px solid var(--border);}
  td{padding:12px 14px;border-bottom:1px solid var(--border);font-size:13px;}
  tr:hover td{background:rgba(59,130,246,.04);}
  .mono{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);}
  .badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}
  .badge-ok{background:rgba(16,185,129,.15);color:var(--ok);}
  .badge-warn{background:rgba(245,158,11,.15);color:var(--warn);}
  .result-box{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--ok);margin-top:14px;white-space:pre-wrap;display:none;}
  .result-box.show{display:block;}
  .empty{color:var(--muted);font-size:14px;padding:30px 0;text-align:center;}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-brand">ORCHESTRATOR <span>CORE API</span> — v3.5.0</div>
  <nav class="topbar-nav">
    <a href="/">Dashboard</a>
    <a href="/tablas">Tablas</a>
    <a href="/tokens" class="active">Tokens</a>
    <a href="/databases">Databases</a>
    <a href="/docs">API Docs</a>
  </nav>
</div>

<div class="container">
  <h1>Gestión de Tokens de Acceso</h1>
  <p class="subtitle">Registra y administra tokens de acceso para bots y clientes</p>

  <p class="section-title">Registrar Nuevo Token</p>
  <div class="card">
    <div class="form-row">
      <div class="form-group">
        <label>NOMBRE DEL BOT / CLIENTE</label>
        <input id="tokenNombre" placeholder="bot_consulta_dni"/>
      </div>
      <div class="form-group">
        <label>TOKEN</label>
        <input id="tokenValor" placeholder="tk_xxxxxxxxxxxxx"/>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>PLAN</label>
        <select id="tokenPlan">
          <option value="basic">Basic</option>
          <option value="pro">Pro</option>
          <option value="enterprise">Enterprise</option>
        </select>
      </div>
      <div class="form-group">
        <label>LÍMITE DIARIO (consultas)</label>
        <input id="tokenLimite" type="number" placeholder="1000" value="1000"/>
      </div>
    </div>
    <div class="actions">
      <button class="btn btn-primary" onclick="registrarToken()">+ Registrar token</button>
      <button class="btn btn-ghost" onclick="generarToken()">⚡ Generar token aleatorio</button>
    </div>
    <div class="result-box" id="tokenResult"></div>
  </div>

  <p class="section-title">Tokens Registrados</p>
  <div class="card">
    <div class="actions" style="margin-top:0;margin-bottom:14px">
      <button class="btn btn-ghost" onclick="listarTokens()">⟳ Actualizar lista</button>
    </div>
    <div id="tokensContainer">
      <p class="empty">Haz clic en "Actualizar lista" para cargar los tokens</p>
    </div>
  </div>
</div>

<script>
function generarToken() {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let t = 'tk_';
  for(let i=0;i<32;i++) t += chars[Math.floor(Math.random()*chars.length)];
  document.getElementById('tokenValor').value = t;
}

async function registrarToken() {
  const payload = {
    nombre:       document.getElementById('tokenNombre').value.trim(),
    token:        document.getElementById('tokenValor').value.trim(),
    plan:         document.getElementById('tokenPlan').value,
    limite_diario: parseInt(document.getElementById('tokenLimite').value) || 1000,
    activo:       true
  };
  if (!payload.nombre || !payload.token) return alert('Nombre y token son requeridos');

  const res  = await fetch('/api/tabla/metadata_tokens', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  const el   = document.getElementById('tokenResult');
  el.textContent = JSON.stringify(data, null, 2);
  el.style.color = res.ok ? 'var(--ok)' : 'var(--err)';
  el.classList.add('show');
  if (res.ok) listarTokens();
}

async function listarTokens() {
  const res  = await fetch('/api/tabla/metadata_tokens?select=*');
  const data = await res.json();
  const cont = document.getElementById('tokensContainer');

  if (!Array.isArray(data) || data.length === 0) {
    cont.innerHTML = '<p class="empty">No hay tokens registrados aún</p>';
    return;
  }

  let html = '<table><thead><tr><th>Nombre</th><th>Token</th><th>Plan</th><th>Límite</th><th>Estado</th></tr></thead><tbody>';
  data.forEach(t => {
    html += `<tr>
      <td>${t.nombre || '—'}</td>
      <td class="mono">${(t.token||'').substring(0,20)}…</td>
      <td>${t.plan || '—'}</td>
      <td>${t.limite_diario || '—'}</td>
      <td>${t.activo ? '<span class="badge badge-ok">Activo</span>' : '<span class="badge badge-warn">Inactivo</span>'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  cont.innerHTML = html;
}
</script>
</body>
</html>
"""

# ──────────────────────────────────────────────────────────────
# HTML: GESTIÓN DE DATABASES DUCKDB
# ──────────────────────────────────────────────────────────────
HTML_DATABASES = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Orchestrator — Databases</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');
  :root{--bg:#0a0e1a;--surface:#111827;--border:#1e2d45;--accent:#3b82f6;--accent2:#06b6d4;--ok:#10b981;--err:#ef4444;--warn:#f59e0b;--text:#e2e8f0;--muted:#64748b;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:'Space Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
  .topbar{display:flex;align-items:center;justify-content:space-between;padding:18px 32px;border-bottom:1px solid var(--border);background:var(--surface);position:sticky;top:0;z-index:100;}
  .topbar-brand{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent);letter-spacing:.08em;}
  .topbar-brand span{color:var(--muted);}
  .topbar-nav a{color:var(--muted);text-decoration:none;font-size:13px;margin-left:24px;}
  .topbar-nav a:hover{color:var(--text);}
  .topbar-nav a.active{color:var(--accent);}
  .container{max-width:1100px;margin:0 auto;padding:40px 24px;}
  h1{font-size:26px;font-weight:700;margin-bottom:6px;}
  .subtitle{color:var(--muted);font-size:14px;margin-bottom:40px;}
  .section-title{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--border);}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:20px;}
  .form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;}
  .form-group{display:flex;flex-direction:column;gap:6px;}
  label{font-size:12px;color:var(--muted);letter-spacing:.04em;}
  input{background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:10px 12px;font-size:13px;font-family:inherit;outline:none;transition:border-color .2s;}
  input:focus{border-color:var(--accent);}
  .btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none;transition:opacity .2s;}
  .btn:hover{opacity:.85;}
  .btn-primary{background:var(--accent);color:#fff;}
  .btn-cyan{background:var(--accent2);color:#000;}
  .btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border);}
  .actions{display:flex;gap:10px;margin-top:14px;}
  .result-box{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--ok);margin-top:14px;white-space:pre-wrap;display:none;}
  .result-box.show{display:block;}
  .db-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;}
  .db-card{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:18px;}
  .db-name{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:700;color:var(--accent2);margin-bottom:6px;}
  .db-meta{font-size:12px;color:var(--muted);line-height:1.6;}
  .badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}
  .badge-ok{background:rgba(16,185,129,.15);color:var(--ok);}
  .empty{color:var(--muted);font-size:14px;padding:30px 0;text-align:center;}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-brand">ORCHESTRATOR <span>CORE API</span> — v3.5.0</div>
  <nav class="topbar-nav">
    <a href="/">Dashboard</a>
    <a href="/tablas">Tablas</a>
    <a href="/tokens">Tokens</a>
    <a href="/databases" class="active">Databases</a>
    <a href="/docs">API Docs</a>
  </nav>
</div>

<div class="container">
  <h1>Bases de Datos DuckDB</h1>
  <p class="subtitle">Registra y activa archivos .duckdb en el catálogo del sistema</p>

  <p class="section-title">Configurar Nueva Base de Datos</p>
  <div class="card">
    <div class="form-row">
      <div class="form-group">
        <label>NOMBRE DEL ARCHIVO (.duckdb)</label>
        <input id="dbNombre" placeholder="datos_reniec_2024.duckdb"/>
      </div>
      <div class="form-group">
        <label>CONTRASEÑA DE DESCARGA</label>
        <input id="dbPassword" type="password" placeholder="pass_seguro_para_bots"/>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>CATEGORÍA</label>
        <input id="dbCategoria" placeholder="reniec, sunat, padron"/>
      </div>
      <div class="form-group">
        <label>URL DE IMAGEN (tarjeta visual)</label>
        <input id="dbImagen" placeholder="https://ejemplo.com/imagen.jpg"/>
      </div>
    </div>
    <div class="actions">
      <button class="btn btn-primary" onclick="configurarDB()">+ Registrar base de datos</button>
    </div>
    <div class="result-box" id="dbResult"></div>
  </div>

  <p class="section-title">Catálogo de Bases de Datos</p>
  <div class="card">
    <div class="actions" style="margin-top:0;margin-bottom:14px">
      <button class="btn btn-ghost" onclick="listarDbs()">⟳ Actualizar catálogo</button>
    </div>
    <div id="dbsContainer">
      <p class="empty">Haz clic en "Actualizar catálogo" para ver las bases de datos registradas</p>
    </div>
  </div>
</div>

<script>
async function configurarDB() {
  const nombre   = document.getElementById('dbNombre').value.trim();
  const password = document.getElementById('dbPassword').value.trim();
  const categoria= document.getElementById('dbCategoria').value.trim();
  const imagen   = document.getElementById('dbImagen').value.trim();
  if (!nombre || !password) return alert('Nombre y contraseña son requeridos');

  const form = new URLSearchParams();
  form.append('nombre_db', nombre);
  form.append('password_descarga', password);
  form.append('categoria', categoria);
  form.append('imagen_url', imagen);

  const res  = await fetch('/api/database/configure', {method:'POST', body: form});
  const data = await res.json();
  const el   = document.getElementById('dbResult');
  el.textContent = JSON.stringify(data, null, 2);
  el.style.color = res.ok ? 'var(--ok)' : 'var(--err)';
  el.classList.add('show');
  if (res.ok) listarDbs();
}

async function listarDbs() {
  const res  = await fetch('/api/tabla/metadata_dbs?select=*');
  const data = await res.json();
  const cont = document.getElementById('dbsContainer');

  if (!Array.isArray(data) || data.length === 0) {
    cont.innerHTML = '<p class="empty">No hay bases de datos registradas aún</p>';
    return;
  }

  let html = '<div class="db-grid">';
  data.forEach(db => {
    html += `<div class="db-card">
      <div class="db-name">${db.nombre_db || db.nombre || '—'}</div>
      <div class="db-meta">
        Categoría: ${db.categoria || '—'}<br/>
        ${db.activo ? '<span class="badge badge-ok">Activo</span>' : ''}
      </div>
    </div>`;
  });
  html += '</div>';
  cont.innerHTML = html;
}
</script>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────
# RUTAS DE VISTAS (HTML Pages)
# ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTML_DASHBOARD

@app.get("/tablas", response_class=HTMLResponse)
async def tablas_page():
    return HTML_TABLAS

@app.get("/tokens", response_class=HTMLResponse)
async def tokens_page():
    return HTML_TOKENS

@app.get("/databases", response_class=HTMLResponse)
async def databases_page():
    return HTML_DATABASES


# ──────────────────────────────────────────────────────────────
# API: CHEQUEO DEL SISTEMA
# ──────────────────────────────────────────────────────────────
@app.get("/api/check")
async def check_sistema():
    checks = []

    def ping(nombre, url, endpoint_label=None):
        try:
            r = requests.get(url, headers=HEADERS, timeout=6)
            ok = r.status_code in (200, 206)
            checks.append({
                "nombre":   nombre,
                "endpoint": endpoint_label or url,
                "ok":       ok,
                "detalle":  f"HTTP {r.status_code}",
            })
        except Exception as e:
            checks.append({
                "nombre":   nombre,
                "endpoint": endpoint_label or url,
                "ok":       False,
                "detalle":  str(e)[:80],
            })

    ping("Supabase REST",    f"{SUPABASE_URL}/rest/v1/",               "/rest/v1/")
    ping("DuckDB API",       f"{DUCKDB_API_URL}/health",               "/health")
    ping("metadata_dbs",     f"{SUPABASE_URL}/rest/v1/metadata_dbs?select=id&limit=1", "metadata_dbs")
    ping("metadata_tokens",  f"{SUPABASE_URL}/rest/v1/metadata_tokens?select=id&limit=1", "metadata_tokens")

    return {"checks": checks}


# ──────────────────────────────────────────────────────────────
# API: EJECUTAR SQL REMOTO (vía RPC)
# ──────────────────────────────────────────────────────────────
@app.post("/api/sql")
async def ejecutar_sql(request: Request):
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(400, "query vacía")

    # Intento 1: endpoint /rest/v1/sql (Supabase ≥ 2.x)
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/sql",
        headers=HEADERS,
        json={"query": query},
        timeout=10,
    )

    if r.status_code == 404:
        # Intento 2: RPC función ejecutar_sql_remoto
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/ejecutar_sql_remoto",
            headers=HEADERS,
            json={"query": query},
            timeout=10,
        )

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    return JSONResponse(content={"status": r.status_code, "data": data}, status_code=200)


# ──────────────────────────────────────────────────────────────
# API: CRUD GENÉRICO SOBRE CUALQUIER TABLA
# ──────────────────────────────────────────────────────────────
@app.get("/api/tabla/{tabla}")
async def leer_tabla(tabla: str, request: Request):
    qs  = str(request.url.query)
    url = f"{SUPABASE_URL}/rest/v1/{tabla}{'?' + qs if qs else '?select=*'}"
    r   = requests.get(url, headers=HEADERS, timeout=10)
    try:
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception:
        return JSONResponse(content={"raw": r.text}, status_code=r.status_code)


@app.post("/api/tabla/{tabla}")
async def insertar_en_tabla(tabla: str, request: Request):
    payload = await request.json()
    hdrs    = {**HEADERS, "Prefer": "return=representation"}
    r       = requests.post(
        f"{SUPABASE_URL}/rest/v1/{tabla}",
        headers=hdrs,
        json=payload,
        timeout=10,
    )
    try:
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception:
        return JSONResponse(content={"raw": r.text}, status_code=r.status_code)


# ──────────────────────────────────────────────────────────────
# API: CONFIGURAR BASE DE DATOS DUCKDB (Form → Supabase)
# ──────────────────────────────────────────────────────────────
@app.post("/api/database/configure")
async def configurar_database(
    nombre_db:         str = Form(...),
    password_descarga: str = Form(...),
    categoria:         str = Form(""),
    imagen_url:        str = Form(""),
):
    payload = {
        "nombre_db":         nombre_db,
        "password_descarga": password_descarga,
        "categoria":         categoria,
        "imagen_url":        imagen_url,
        "activo":            True,
    }
    hdrs = {**HEADERS, "Prefer": "return=representation"}
    r    = requests.post(
        f"{SUPABASE_URL}/rest/v1/metadata_dbs",
        headers=hdrs,
        json=payload,
        timeout=10,
    )
    try:
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception:
        return JSONResponse(content={"raw": r.text}, status_code=r.status_code)


# ──────────────────────────────────────────────────────────────
# API: CREAR TABLAS BASE DEL SISTEMA (acción rápida del dashboard)
# ──────────────────────────────────────────────────────────────
TABLAS_BASE = {
    "metadata_dbs": """
        CREATE TABLE IF NOT EXISTS public.metadata_dbs (
            id                BIGSERIAL PRIMARY KEY,
            nombre_db         TEXT NOT NULL,
            password_descarga TEXT,
            categoria         TEXT,
            imagen_url        TEXT,
            activo            BOOLEAN DEFAULT TRUE,
            creado_en         TIMESTAMPTZ DEFAULT NOW()
        );
    """,
    "metadata_tokens": """
        CREATE TABLE IF NOT EXISTS public.metadata_tokens (
            id            BIGSERIAL PRIMARY KEY,
            nombre        TEXT NOT NULL,
            token         TEXT UNIQUE NOT NULL,
            plan          TEXT DEFAULT 'basic',
            limite_diario INTEGER DEFAULT 1000,
            activo        BOOLEAN DEFAULT TRUE,
            creado_en     TIMESTAMPTZ DEFAULT NOW()
        );
    """,
}

@app.post("/api/crear-tablas")
async def crear_tablas_base():
    resultados = []
    for nombre, sql in TABLAS_BASE.items():
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/sql",
            headers=HEADERS,
            json={"query": sql.strip()},
            timeout=10,
        )
        if r.status_code == 404:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/rpc/ejecutar_sql_remoto",
                headers=HEADERS,
                json={"query": sql.strip()},
                timeout=10,
            )
        ok = r.status_code in (200, 201, 204)
        resultados.append({
            "tabla":  nombre,
            "ok":     ok,
            "status": r.status_code,
            "msg":    f"Tabla '{nombre}': {'✅ OK' if ok else '❌ ERROR'} (HTTP {r.status_code})",
        })
    return {"resultados": resultados}


# ──────────────────────────────────────────────────────────────
# ARRANQUE LOCAL
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
