#!/usr/bin/env python3
"""xHAL2049 Web Console — upload files, process with sopx, watch progress.

Usage:
    python scripts/web_server.py [--port 8080]

Opens a browser with:
    - xHAL2049 banner
    - Drag & drop / file upload
    - Live console showing progress
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "_web_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# SSE event queues per session
_sessions: dict[str, queue.Queue] = {}


def _html_page() -> str:
    return r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>xHAL2049 — SOP Extractor</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0a0a0f;color:#e0e0e0;font-family:'Fira Code','Cascadia Code','JetBrains Mono',monospace;min-height:100vh;display:flex;flex-direction:column}
  .banner{text-align:center;padding:24px 16px 8px;border-bottom:1px solid #1a1a2e}
  .banner h1{font-size:28px;letter-spacing:4px;background:linear-gradient(90deg,#00d4ff,#7b2ff7,#ff0080);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-transform:uppercase}
  .banner .sub{font-size:11px;color:#555;margin-top:4px;letter-spacing:2px}
  .main{flex:1;display:flex;flex-direction:column;max-width:900px;width:100%;margin:0 auto;padding:16px}
  .upload-zone{border:2px dashed #2a2a4a;border-radius:12px;padding:40px 20px;text-align:center;cursor:pointer;transition:all .2s;margin-bottom:16px;position:relative}
  .upload-zone:hover,.upload-zone.dragover{border-color:#7b2ff7;background:rgba(123,47,247,.08)}
  .upload-zone .icon{font-size:48px;margin-bottom:12px}
  .upload-zone .label{font-size:14px;color:#888}
  .upload-zone .label b{color:#00d4ff}
  .upload-zone input{position:absolute;inset:0;opacity:0;cursor:pointer}
  .files-list{margin-bottom:12px;font-size:12px;color:#888;min-height:20px}
  .files-list .file{display:inline-block;background:#1a1a2e;padding:3px 10px;border-radius:6px;margin:2px 4px}
  .actions{display:flex;gap:10px;margin-bottom:16px;align-items:center}
  .btn{padding:10px 24px;border:none;border-radius:8px;font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;letter-spacing:1px}
  .btn-primary{background:linear-gradient(135deg,#7b2ff7,#00d4ff);color:#fff}
  .btn-primary:hover{opacity:.85;transform:translateY(-1px)}
  .btn-primary:disabled{opacity:.3;cursor:not-allowed;transform:none}
  .btn-danger{background:#ff006633;color:#ff4488;border:1px solid #ff448844}
  .btn-danger:hover{background:#ff006655}
  .status{font-size:12px;color:#555;padding:8px 0}
  .status .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
  .dot-idle{background:#444}
  .dot-running{background:#00d4ff;animation:pulse 1s infinite}
  .dot-done{background:#00ff88}
  .dot-error{background:#ff4444}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .console{flex:1;background:#050508;border:1px solid #1a1a2e;border-radius:10px;padding:12px 16px;overflow-y:auto;font-size:12px;line-height:1.7;min-height:300px;max-height:70vh}
  .console .line{white-space:pre-wrap;word-break:break-all}
  .console .line.info{color:#00d4ff}
  .console .line.ok{color:#00ff88}
  .console .line.warn{color:#ffaa00}
  .console .line.err{color:#ff4444}
  .console .line.dim{color:#444}
  .console .ts{color:#333;margin-right:6px}
  .footer{text-align:center;padding:12px;font-size:10px;color:#333;border-top:1px solid #1a1a2e}
  .results{margin-top:16px;padding:16px;background:#0a0a12;border:1px solid #1a1a2e;border-radius:10px}
  .results-btns{display:flex;gap:10px;flex-wrap:wrap}
  .btn-result{background:#1a1a2e;color:#e0e0e0;padding:10px 20px;border:1px solid #2a2a4a;border-radius:8px;text-decoration:none;font-family:inherit;font-size:12px;cursor:pointer;transition:all .15s;display:inline-block}
  .btn-result:hover{background:#2a2a4a;border-color:#7b2ff7;transform:translateY(-1px)}
</style>
</head>
<body>
<div class="banner">
  <h1>xHAL2049</h1>
  <div class="sub">SOP EXTRACTOR — KNOWLEDGE COMPILATION CONSOLE</div>
  <a href="/settings" style="position:absolute;top:16px;right:24px;color:#555;text-decoration:none;font-size:13px" onmouseover="this.style.color='#00d4ff'" onmouseout="this.style.color='#555'">⚙ Config</a>
</div>

<div class="main">
  <div class="upload-zone" id="dropZone">
    <div class="icon">📁</div>
    <div class="label">Arraste arquivos aqui ou <b>clique para selecionar</b></div>
    <div class="label" style="margin-top:6px;font-size:11px;color:#444">PDF, EPUB, DOCX, TXT, SRT, MD, MP3, WAV, MP4 — ou URL do YouTube</div>
    <input type="file" id="fileInput" multiple accept=".pdf,.epub,.docx,.txt,.srt,.vtt,.md,.rst,.html,.mp3,.wav,.m4a,.ogg,.flac,.mp4,.mkv,.avi,.mov">
  </div>

  <div class="files-list" id="filesList"></div>

  <div class="actions">
    <button class="btn btn-primary" id="processBtn" disabled>▶ PROCESSAR</button>
    <button class="btn btn-danger" id="clearBtn" style="display:none">✕ LIMPAR</button>
    <div class="status" id="status"><span class="dot dot-idle"></span>Pronto</div>
    <div id="apiKeyStatus" style="margin-left:auto;font-size:11px"></div>
  </div>

  <div class="console" id="console"></div>

  <div class="results" id="results" style="display:none">
    <div style="font-size:12px;color:#555;margin-bottom:8px;letter-spacing:1px">RESULTADOS</div>
    <div class="results-btns">
      <a class="btn btn-result" id="btnSkill" href="#" target="_blank">📄 Ver Skill</a>
      <a class="btn btn-result" id="btnGraph" href="#" target="_blank">🕸 Ver Grafo</a>
      <a class="btn btn-result" id="btnSummary" href="#" target="_blank">📊 Ver Summary</a>
      <a class="btn btn-result" id="btnSF" href="#" target="_blank">🧠 Semantic Field</a>
    </div>
  </div>
</div>

<div class="footer">sop-extractor v3.1.0 — knowledge compilation engine</div>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const filesList = document.getElementById('filesList');
const processBtn = document.getElementById('processBtn');
const clearBtn = document.getElementById('clearBtn');
const statusEl = document.getElementById('status');
const consoleEl = document.getElementById('console');
let selectedFiles = [];
let sessionId = null;
let eventSource = null;

// Drag & drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', e => addFiles(e.target.files));

function addFiles(fileList) {
  for (const f of fileList) {
    if (!selectedFiles.find(s => s.name === f.name && s.size === f.size)) {
      selectedFiles.push(f);
    }
  }
  renderFiles();
}

function renderFiles() {
  if (selectedFiles.length === 0) {
    filesList.innerHTML = '';
    processBtn.disabled = true;
    clearBtn.style.display = 'none';
    return;
  }
  filesList.innerHTML = selectedFiles.map(f =>
    `<span class="file">${f.name} (${(f.size/1024).toFixed(0)}KB)</span>`
  ).join('');
  processBtn.disabled = false;
  clearBtn.style.display = '';
}

clearBtn.addEventListener('click', () => {
  selectedFiles = [];
  fileInput.value = '';
  renderFiles();
  consoleEl.innerHTML = '';
  setStatus('idle', 'Pronto');
});

processBtn.addEventListener('click', () => {
  if (selectedFiles.length === 0) return;
  processBtn.disabled = true;
  setStatus('running', 'Processando...');
  log('info', `▶ Iniciando pipeline — ${selectedFiles.length} arquivo(s)`);
  uploadAndProcess();
});

async function uploadAndProcess() {
  const formData = new FormData();
  for (const f of selectedFiles) {
    formData.append('files', f);
  }

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();
    sessionId = data.session_id;
    log('info', `Sessão: ${sessionId}`);
    log('info', `Arquivos: ${data.files.map(f => f.name).join(', ')}`);
    log('dim', '─'.repeat(50));
    listenProgress(sessionId);
  } catch (err) {
    log('err', `Erro no upload: ${err.message}`);
    setStatus('error', 'Erro no upload');
    processBtn.disabled = false;
  }
}

function listenProgress(sid) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/progress/${sid}`);
  eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'line') {
      log(data.level || 'info', data.text);
    } else if (data.type === 'done') {
      log('ok', '─'.repeat(50));
      log('ok', `✓ Pipeline concluído — ${data.message || 'sucesso'}`);
      setStatus('done', 'Concluído');
      processBtn.disabled = false;
      showResults(sid);
      if (eventSource) eventSource.close();
    } else if (data.type === 'error') {
      log('err', `✗ ${data.message}`);
      setStatus('error', 'Erro');
      processBtn.disabled = false;
      if (eventSource) eventSource.close();
    }
  };
  eventSource.onerror = () => {
    // SSE connection closed — normal after completion
  };
}

function showResults(sid) {
  const resultsEl = document.getElementById('results');
  resultsEl.style.display = '';
  document.getElementById('btnSkill').href = `/results/${sid}/skill`;
  document.getElementById('btnGraph').href = `/results/${sid}/graph`;
  document.getElementById('btnSummary').href = `/results/${sid}/summary`;
  document.getElementById('btnSF').href = `/results/${sid}/sf`;
}

function log(level, text) {
  const ts = new Date().toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const line = document.createElement('div');
  line.className = `line ${level}`;
  line.innerHTML = `<span class="ts">${ts}</span>${escapeHtml(text)}`;
  consoleEl.appendChild(line);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

function escapeHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setStatus(state, text) {
  statusEl.innerHTML = `<span class="dot dot-${state}"></span>${text}`;
}
</script>

<script>
// Check API key status on load
fetch('/api/settings').then(r=>r.json()).then(d=>{
  const el = document.getElementById('apiKeyStatus');
  if(d.has_key) {
    el.innerHTML = '<span style="color:#00ff88">✓ API key configurada</span>';
  } else {
    el.innerHTML = '<span style="color:#ffaa00">⚠ Sem API key — <a href="/settings" style="color:#00d4ff">configurar</a></span>';
  }
});
</script>
</body>
</html>"""


SETTINGS_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>xHAL2049 — Configuração</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0a0a0f;color:#e0e0e0;font-family:'Fira Code','Cascadia Code',monospace;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:40px 16px}
  .card{background:#0d0d14;border:1px solid #1a1a2e;border-radius:12px;padding:32px;max-width:560px;width:100%}
  h1{font-size:20px;color:#00d4ff;margin-bottom:4px}
  .sub{font-size:11px;color:#555;margin-bottom:24px}
  label{display:block;font-size:12px;color:#888;margin-bottom:6px;letter-spacing:1px}
  input[type=text]{width:100%;padding:10px 14px;background:#050508;border:1px solid #2a2a4a;border-radius:8px;color:#e0e0e0;font-family:inherit;font-size:13px;outline:none}
  input[type=text]:focus{border-color:#7b2ff7}
  .hint{font-size:11px;color:#444;margin-top:6px}
  .btn{padding:10px 24px;border:none;border-radius:8px;font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;margin-top:16px}
  .btn-primary{background:linear-gradient(135deg,#7b2ff7,#00d4ff);color:#fff}
  .btn-primary:hover{opacity:.85}
  .btn-back{background:transparent;color:#888;border:1px solid #2a2a4a;margin-right:8px}
  .btn-back:hover{color:#e0e0e0;border-color:#555}
  .status{margin-top:12px;font-size:12px}
  .status.ok{color:#00ff88}
  .status.err{color:#ff4444}
  .presets{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
  .preset{padding:4px 10px;background:#1a1a2e;border:1px solid #2a2a4a;border-radius:6px;font-size:11px;color:#888;cursor:pointer;transition:all .15s}
  .preset:hover{border-color:#7b2ff7;color:#e0e0e0}
  .preset.active{border-color:#00d4ff;color:#00d4ff}
</style>
</head>
<body>
<div class="card">
  <h1>⚙ Configuração</h1>
  <div class="sub">xHAL2049 — BYOK (Bring Your Own Key) — qualquer provider OpenAI-compatível</div>

  <form id="settingsForm">
    <label>BASE URL DA API</label>
    <input type="text" id="baseUrl" placeholder="https://api.anthropic.com">
    <div class="hint">URL base do endpoint. Qualquer API OpenAI-compatível funciona.</div>

    <div class="presets">
      <span class="preset" onclick="setPreset('https://api.anthropic.com','Anthropic')">Anthropic</span>
      <span class="preset" onclick="setPreset('https://api.openai.com','OpenAI')">OpenAI</span>
      <span class="preset" onclick="setPreset('https://integrate.api.nvidia.com/v1','Nvidia')">Nvidia NIM</span>
      <span class="preset" onclick="setPreset('https://generativelanguage.googleapis.com','Gemini')">Gemini</span>
      <span class="preset" onclick="setPreset('https://api.minimax.chat','Minimax')">Minimax</span>
      <span class="preset" onclick="setPreset('https://api.xiaomi.com','MiMo')">MiMo</span>
      <span class="preset" onclick="setPreset('https://api.groq.com/openai','Groq')">Groq</span>
      <span class="preset" onclick="setPreset('http://localhost:11434','Ollama')">Ollama</span>
      <span class="preset" onclick="setPreset('https://api.deepseek.com','DeepSeek')">DeepSeek</span>
    </div>

    <label style="margin-top:16px">API KEY</label>
    <input type="text" id="apiKey" placeholder="sk-..." autocomplete="off">
    <div class="hint">Sua chave fica salva apenas neste servidor local.</div>

    <label style="margin-top:16px">MODEL ID</label>
    <input type="text" id="model" placeholder="ex: meta/llama-3.1-70b-instruct">
    <div class="hint">ID do modelo conforme a API do provider.</div>

    <div class="presets" id="modelPresets"></div>

    <div style="display:flex;gap:10px;margin-top:20px">
      <button type="button" class="btn btn-back" onclick="location.href='/'">← Voltar</button>
      <button type="submit" class="btn btn-primary">Salvar</button>
    </div>
  </form>
  <div class="status" id="status"></div>
</div>

<script>
const MODEL_PRESETS = {
  'Anthropic': ['claude-sonnet-4-20250514','claude-3-5-sonnet-20241022','claude-3-haiku-20240307'],
  'OpenAI': ['gpt-4o','gpt-4o-mini','gpt-4-turbo'],
  'Nvidia': ['nvidia/llama-3.1-nemotron-ultra-253b-v1','meta/llama-3.1-70b-instruct','nvidia/llama-3.3-nemotron-super-49b-v1'],
  'Gemini': ['gemini-2.5-pro','gemini-2.5-flash','gemini-2.0-flash'],
  'Minimax': ['MiniMax-Text-01','abab6.5s-chat'],
  'MiMo': ['mimo-v2.5','mimo-v2.5-pro'],
  'Groq': ['llama-3.3-70b-versatile','mixtral-8x7b-32768','gemma2-9b-it'],
  'Ollama': ['llama3.1','mistral','codellama','gemma2'],
  'DeepSeek': ['deepseek-chat','deepseek-reasoner'],
};

function setPreset(url, name) {
  document.getElementById('baseUrl').value = url;
  document.querySelectorAll('.preset').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  // Show model presets
  const models = MODEL_PRESETS[name] || [];
  const el = document.getElementById('modelPresets');
  el.innerHTML = models.map(m =>
    `<span class="preset" onclick="document.getElementById('model').value='${m}'">${m}</span>`
  ).join('');
}

// Load current settings
fetch('/api/settings').then(r=>r.json()).then(d=>{
  if(d.base_url) document.getElementById('baseUrl').value = d.base_url;
  if(d.model) document.getElementById('model').value = d.model;
  if(d.has_key) document.getElementById('apiKey').placeholder = '•••••••••••••••• (já configurada)';
});

document.getElementById('settingsForm').addEventListener('submit', async(e)=>{
  e.preventDefault();
  const key = document.getElementById('apiKey').value.trim();
  const base_url = document.getElementById('baseUrl').value.trim();
  const model = document.getElementById('model').value.trim();
  const body = {base_url, model};
  if(key) body.api_key = key;

  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json();
  const statusEl = document.getElementById('status');
  if(data.ok) {
    statusEl.className = 'status ok';
    statusEl.textContent = '✓ Salvo com sucesso';
    if(key) document.getElementById('apiKey').value = '';
  } else {
    statusEl.className = 'status err';
    statusEl.textContent = '✗ ' + (data.error || 'Erro ao salvar');
  }
});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

SETTINGS_PATH = os.path.join(UPLOAD_DIR, "_settings.json")


def _load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_settings(data: dict):
    current = _load_settings()
    current.update(data)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)


class Session:
    def __init__(self, sid: str, files: list[Path]):
        self.sid = sid
        self.files = files
        self.q: queue.Queue = queue.Queue()
        self.done = False
        self.error = None
        self.output_dir: Path | None = None

    def emit(self, level: str, text: str):
        self.q.put({"type": "line", "level": level, "text": text})

    def finish(self, message: str = "sucesso"):
        self.q.put({"type": "done", "message": message})
        self.done = True

    def fail(self, message: str):
        self.q.put({"type": "error", "message": message})
        self.done = True
        self.error = message


def _run_pipeline(session: Session):
    """Run sopx run on each uploaded file in a thread."""
    try:
        # Load API settings
        settings = _load_settings()
        env = os.environ.copy()
        if settings.get("api_key"):
            env["LLM_API_KEY"] = settings["api_key"]
        if settings.get("base_url"):
            env["LLM_BASE_URL"] = settings["base_url"]
        if settings.get("model"):
            env["LLM_MODEL"] = settings["model"]

        for f in session.files:
            session.emit("info", f"▸ Processando: {f.name}")
            cmd = [
                sys.executable, os.path.join(SCRIPTS_DIR, "run.py"),
                str(f),
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=PROJECT_ROOT, env=env,
            )
            for line in proc.stdout:
                text = line.rstrip()
                session.emit("info", text)
                # Track output dir from batch summary path
                if "Batch summary:" in text or "batch_summary" in text:
                    try:
                        summary_path = text.split(":")[-1].strip()
                        session.output_dir = Path(summary_path).parent.parent
                    except Exception:
                        pass
            proc.wait()
            if proc.returncode != 0:
                session.emit("warn", f"⚠ {f.name} retornou exit code {proc.returncode}")
            else:
                session.emit("ok", f"✓ {f.name} concluído")

        # Find output dir from upload directory
        if not session.output_dir:
            upload_dir = Path(session.files[0]).parent
            compilation = upload_dir / "compilation"
            if compilation.exists():
                session.output_dir = upload_dir

        session.finish(f"{len(session.files)} arquivo(s) processado(s)")
    except Exception as e:
        session.fail(str(e))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence request logs

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_html_page().encode())

        elif path == "/settings":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SETTINGS_HTML.encode())

        elif path == "/api/settings":
            settings = _load_settings()
            resp = json.dumps({
                "base_url": settings.get("base_url", ""),
                "model": settings.get("model", ""),
                "has_key": bool(settings.get("api_key")),
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.encode())

        elif path.startswith("/progress/"):
            sid = path.split("/")[-1]
            session = _sessions.get(sid)
            if not session:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            while not session.done:
                try:
                    event = session.q.get(timeout=1)
                    data = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()

            # Send final events
            while not session.q.empty():
                event = session.q.get()
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

        elif path.startswith("/results/") and path.endswith("/skill"):
            sid = path.split("/")[2]
            self._serve_skill(sid)

        elif path.startswith("/results/") and path.endswith("/graph"):
            sid = path.split("/")[2]
            self._serve_graph(sid)

        elif path.startswith("/results/") and path.endswith("/summary"):
            sid = path.split("/")[2]
            self._serve_summary(sid)

        elif path.startswith("/results/") and path.endswith("/sf"):
            sid = path.split("/")[2]
            self._serve_sf(sid)

        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, file_path: Path, content_type: str):
        if not file_path.exists():
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Arquivo não encontrado: {file_path.name}".encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _serve_skill(self, sid: str):
        session = _sessions.get(sid)
        if not session or not session.output_dir:
            self.send_response(404)
            self.end_headers()
            return
        # Look for rendered HTML or SKILL.md
        compilation = session.output_dir / "compilation"
        html_files = list(compilation.glob("*.html")) if compilation.exists() else []
        if html_files:
            self._serve_file(html_files[0], "text/html; charset=utf-8")
        elif (compilation / "SKILL.md").exists():
            self._serve_file(compilation / "SKILL.md", "text/markdown; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_graph(self, sid: str):
        session = _sessions.get(sid)
        if not session or not session.output_dir:
            self.send_response(404)
            self.end_headers()
            return
        compilation = session.output_dir / "compilation"
        graph_files = list(compilation.glob("*.html")) if compilation.exists() else []
        sf_html = compilation / "semantic_field.html" if compilation.exists() else None
        if sf_html and sf_html.exists():
            self._serve_file(sf_html, "text/html; charset=utf-8")
        elif graph_files:
            self._serve_file(graph_files[-1], "text/html; charset=utf-8")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Grafo não disponível</h3><p>Execute a compilacao com semantic field habilitado.</p>".encode())

    def _serve_summary(self, sid: str):
        session = _sessions.get(sid)
        if not session or not session.output_dir:
            self.send_response(404)
            self.end_headers()
            return
        compilation = session.output_dir / "compilation"
        summary = compilation / "batch_summary.md" if compilation.exists() else None
        run_json = compilation / "run.json" if compilation.exists() else None
        if summary and summary.exists():
            md = summary.read_text(encoding="utf-8")
            # Convert simple markdown to HTML
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Summary</title>
<style>body{{font-family:monospace;background:#0a0a0f;color:#e0e0e0;padding:24px;max-width:800px;margin:auto}}
h1,h2,h3{{color:#00d4ff}}pre{{background:#050508;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #1a1a2e;padding:8px;text-align:left}}</style>
</head><body><pre>{md}</pre></body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif run_json and run_json.exists():
            self._serve_file(run_json, "application/json")
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_sf(self, sid: str):
        session = _sessions.get(sid)
        if not session or not session.output_dir:
            self.send_response(404)
            self.end_headers()
            return
        compilation = session.output_dir / "compilation"
        sf_json = compilation / "semantic_field.json" if compilation.exists() else None
        if sf_json and sf_json.exists():
            self._serve_file(sf_json, "application/json")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Semantic Field não disponível</h3><p>Sem dados de semantic field nesta sessao.</p>".encode())

    def do_POST(self):
        if self.path == "/api/settings":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                update = {}
                if "api_key" in data and data["api_key"]:
                    update["api_key"] = data["api_key"]
                if "base_url" in data:
                    update["base_url"] = data["base_url"]
                if "model" in data:
                    update["model"] = data["model"]
                _save_settings(update)
                resp = json.dumps({"ok": True})
            except Exception as e:
                resp = json.dumps({"ok": False, "error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.encode())
            return

        if self.path == "/upload":
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_response(400)
                self.end_headers()
                return

            boundary = content_type.split("boundary=")[1].encode()
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # Parse multipart manually (stdlib only)
            files = []
            parts = body.split(b"--" + boundary)
            for part in parts:
                if b"Content-Disposition" not in part:
                    continue
                header_end = part.find(b"\r\n\r\n")
                if header_end == -1:
                    continue
                header = part[:header_end].decode(errors="replace")
                file_data = part[header_end + 4:]
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]

                # Extract filename
                if 'filename="' not in header:
                    continue
                filename = header.split('filename="')[1].split('"')[0]
                if not filename:
                    continue

                # Save to upload dir
                sid = uuid.uuid4().hex[:8]
                save_dir = os.path.join(UPLOAD_DIR, sid)
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, filename)
                with open(save_path, "wb") as f:
                    f.write(file_data)
                files.append(Path(save_path))

            if not files:
                self.send_response(400)
                self.end_headers()
                return

            # Create session and start pipeline
            session_id = uuid.uuid4().hex[:8]
            session = Session(session_id, files)
            _sessions[session_id] = session

            thread = threading.Thread(target=_run_pipeline, args=(session,), daemon=True)
            thread.start()

            response = json.dumps({
                "session_id": session_id,
                "files": [{"name": f.name, "size": f.stat().st_size} for f in files],
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response.encode())

        else:
            self.send_response(404)
            self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="xHAL2049 Web Console")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"

    print("\n  ╔══════════════════════════════════════════╗")
    print("  ║  xHAL2049 — SOP Extractor Web Console   ║")
    print("  ╚══════════════════════════════════════════╝")
    print(f"\n  → {url}")
    print("  Ctrl+C para sair\n")

    if not args.no_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Encerrado.")
        server.server_close()


if __name__ == "__main__":
    main()
