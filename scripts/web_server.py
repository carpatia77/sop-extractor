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

# Teach mode sessions
_teach_sessions: dict[str, dict] = {}


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
      <a class="btn btn-result" href="/teach" target="_blank" style="border-color:#ff0080;color:#ff0080">🎓 Teach Mode</a>
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


# ---------------------------------------------------------------------------
# Cyberpunk HTML renderers
# ---------------------------------------------------------------------------

_TEACH_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>xHAL2049 — Teach Mode</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Share Tech Mono',monospace;background:#06060c;color:#e0e0e0;height:100vh;display:flex;flex-direction:column}
#grid{position:fixed;inset:0;background-image:
  linear-gradient(rgba(0,212,255,.03) 1px,transparent 1px),
  linear-gradient(90deg,rgba(0,212,255,.03) 1px,transparent 1px);
  background-size:40px 40px;pointer-events:none;z-index:0}
.header{position:relative;z-index:2;padding:12px 24px;background:rgba(6,6,12,.95);
  border-bottom:1px solid rgba(0,212,255,.15);display:flex;align-items:center;gap:16px}
.header h1{font-family:'Orbitron',sans-serif;font-size:14px;letter-spacing:2px;
  background:linear-gradient(90deg,#00d4ff,#ff0080);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header select{background:#0d0d14;border:1px solid #1a1a2e;color:#e0e0e0;
  padding:6px 12px;border-radius:6px;font-family:inherit;font-size:12px}
.header button{padding:6px 16px;border:1px solid #7b2ff7;background:transparent;
  color:#7b2ff7;border-radius:6px;font-family:inherit;font-size:11px;cursor:pointer;
  letter-spacing:1px;transition:all .15s}
.header button:hover{background:#7b2ff722}
.header button.active{background:#7b2ff7;color:#fff}
.back{color:#555;text-decoration:none;font-size:11px;margin-left:auto;letter-spacing:1px}
.back:hover{color:#00d4ff}
.chat{flex:1;overflow-y:auto;padding:24px;position:relative;z-index:1;max-width:800px;
  width:100%;margin:0 auto}
.msg{margin-bottom:16px;padding:14px 18px;border-radius:10px;max-width:85%;
  animation:fadeIn .3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.msg.engine{background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.15);
  align-self:flex-start;border-bottom-left-radius:2px}
.msg.user{background:rgba(123,47,247,.1);border:1px solid rgba(123,47,247,.15);
  margin-left:auto;border-bottom-right-radius:2px}
.msg .sender{font-size:10px;letter-spacing:1px;margin-bottom:6px;text-transform:uppercase}
.msg.engine .sender{color:#00d4ff}
.msg.user .sender{color:#7b2ff7}
.msg .text{font-size:13px;line-height:1.6;color:#ccc}
.msg .meta{font-size:10px;color:#555;margin-top:8px;display:flex;gap:12px}
.msg .depth-badge{padding:2px 8px;border-radius:4px;font-size:10px;letter-spacing:1px}
.depth-0{background:#ff008022;color:#ff0080;border:1px solid #ff008033}
.depth-1{background:#ffaa0022;color:#ffaa00;border:1px solid #ffaa0033}
.depth-2{background:#00d4ff22;color:#00d4ff;border:1px solid #00d4ff33}
.depth-3{background:#00ff8822;color:#00ff88;border:1px solid #00ff8833}
.depth-4{background:#7b2ff722;color:#7b2ff7;border:1px solid #7b2ff733}
.depth-5{background:#ff008022;color:#ff0080;border:1px solid #ff008033}
.depth-6{background:#ffaa0022;color:#ffaa00;border:1px solid #ffaa0033}
.depth-7{background:#00ff8833;color:#00ff88;border:1px solid #00ff8855}
.input-area{position:relative;z-index:2;padding:16px 24px;
  background:rgba(6,6,12,.95);border-top:1px solid rgba(0,212,255,.15)}
.input-row{display:flex;gap:10px;max-width:800px;margin:0 auto}
.input-row textarea{flex:1;background:#0d0d14;border:1px solid #1a1a2e;color:#e0e0e0;
  padding:12px 16px;border-radius:8px;font-family:inherit;font-size:13px;
  resize:none;outline:none;min-height:44px;max-height:120px}
.input-row textarea:focus{border-color:#7b2ff7}
.input-row button{padding:12px 24px;border:none;border-radius:8px;
  background:linear-gradient(135deg,#7b2ff7,#00d4ff);color:#fff;
  font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;
  letter-spacing:1px;transition:all .15s;white-space:nowrap}
.input-row button:hover{opacity:.85}
.input-row button:disabled{opacity:.3;cursor:not-allowed}
.stats-bar{font-size:10px;color:#444;text-align:center;padding:6px;letter-spacing:1px}
</style>
</head>
<body>
<div id="grid"></div>
<div class="header">
  <h1>TEACH MODE</h1>
  <select id="sfSelect"><option value="">Selecione uma skill...</option></select>
  <button id="startBtn" disabled>INICIAR</button>
  <a class="back" href="/">← VOLTAR</a>
</div>
<div class="chat" id="chat">
  <div style="text-align:center;padding:60px 20px;color:#444">
    <div style="font-family:Orbitron;font-size:14px;color:#555;margin-bottom:12px">CHAVRUTA ENGINE</div>
    <div style="font-size:12px">Selecione uma skill compilada e inicie uma sessão de debate.</div>
    <div style="font-size:11px;color:#333;margin-top:8px">O motor Socrático desafia seu conhecimento profundamente.</div>
  </div>
</div>
<div class="input-area">
  <div class="stats-bar" id="statsBar"></div>
  <div class="input-row">
    <textarea id="userInput" placeholder="Digite sua resposta..." rows="1" disabled></textarea>
    <button id="sendBtn" disabled>ENVIAR</button>
  </div>
</div>

<script>
const chat = document.getElementById('chat');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const startBtn = document.getElementById('startBtn');
const sfSelect = document.getElementById('sfSelect');
const statsBar = document.getElementById('statsBar');
let sessionId = null;
let depthHistory = [];

// Load available SFs
fetch('/api/teach/sessions').then(r=>r.json()).then(list => {
  list.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.label;
    opt.dataset.sfPath = s.sf_path;
    sfSelect.appendChild(opt);
  });
  if (list.length > 0) {
    startBtn.disabled = false;
  }
});

startBtn.onclick = async () => {
  const opt = sfSelect.selectedOptions[0];
  if (!opt || !opt.dataset.sfPath) return;
  startBtn.disabled = true;
  startBtn.textContent = 'INICIANDO...';
  const res = await fetch('/api/teach/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sf_path: opt.dataset.sfPath})
  });
  const data = await res.json();
  if (data.ok) {
    sessionId = data.session_id;
    sendBtn.disabled = false;
    userInput.disabled = false;
    userInput.focus();
    addMsg('engine', 'Sessão iniciada. Faça uma afirmação sobre o conteúdo para começarmos o debate.', null);
    startBtn.textContent = 'ATIVO';
    startBtn.classList.add('active');
  }
};

sendBtn.onclick = () => sendResponse();
userInput.onkeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendResponse(); }
};
userInput.oninput = () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
};

async function sendResponse() {
  const text = userInput.value.trim();
  if (!text || !sessionId) return;
  addMsg('user', text);
  userInput.value = '';
  userInput.style.height = 'auto';
  sendBtn.disabled = true;

  const res = await fetch('/api/teach/respond', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id: sessionId, response: text})
  });
  const data = await res.json();
  sendBtn.disabled = false;
  if (data.ok) {
    depthHistory.push(data.depth);
    addMsg('engine', data.challenge, data);
    updateStats(data);
  } else {
    addMsg('engine', 'Erro: ' + data.error, null);
  }
}

function addMsg(sender, text, meta) {
  const div = document.createElement('div');
  div.className = 'msg ' + sender;
  let html = `<div class="sender">${sender === 'engine' ? '⚙ CHAVRUTA' : '✦ VOCÊ'}</div>`;
  html += `<div class="text">${escapeHtml(text)}</div>`;
  if (meta) {
    const depthClass = 'depth-' + meta.depth;
    html += `<div class="meta">
      <span class="depth-badge ${depthClass}">DEPTH ${meta.depth} — ${meta.depth_label}</span>
      <span>${meta.depth_bar}</span>
      ${meta.is_contradiction ? '<span style="color:#ff0080">⚠ CONTRADIÇÃO</span>' : ''}
      ${meta.matched_node ? '<span>Nó: ' + escapeHtml(meta.matched_node) + '</span>' : ''}
    </div>`;
  }
  div.innerHTML = html;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function updateStats(data) {
  const avg = depthHistory.length ? (depthHistory.reduce((a,b)=>a+b,0)/depthHistory.length).toFixed(1) : '0';
  const max = Math.max(...depthHistory);
  statsBar.textContent = `MOVES: ${depthHistory.length} | MAX DEPTH: ${max} | AVG: ${avg}`;
}

function escapeHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}
</script>
</body>
</html>"""


_CYBER_CSS = """\
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Share Tech Mono',monospace;background:#06060c;color:#e0e0e0;min-height:100vh}
#grid{position:fixed;inset:0;background-image:
  linear-gradient(rgba(0,212,255,.03) 1px,transparent 1px),
  linear-gradient(90deg,rgba(0,212,255,.03) 1px,transparent 1px);
  background-size:40px 40px;pointer-events:none;z-index:0}
.wrap{position:relative;z-index:1;max-width:900px;margin:0 auto;padding:24px 20px 60px}
.header{padding:16px 0 20px;border-bottom:1px solid rgba(0,212,255,.15);margin-bottom:24px}
.header h1{font-family:'Orbitron',sans-serif;font-size:18px;letter-spacing:3px;
  background:linear-gradient(90deg,#00d4ff,#7b2ff7,#ff0080);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .meta{font-size:11px;color:#555;margin-top:6px;letter-spacing:1px}
.back{position:fixed;top:16px;right:24px;color:#555;text-decoration:none;font-size:12px;
  z-index:10;letter-spacing:1px}
.back:hover{color:#00d4ff}
h2{font-family:'Orbitron',sans-serif;font-size:14px;color:#00d4ff;margin:28px 0 14px;
  letter-spacing:2px;border-bottom:1px solid rgba(0,212,255,.1);padding-bottom:8px}
h3{font-size:13px;color:#7b2ff7;margin:18px 0 8px;letter-spacing:1px}
h4{font-size:12px;color:#ff0080;margin:14px 0 6px}
p,li{font-size:13px;line-height:1.7;color:#bbb}
ul,ol{padding-left:20px;margin:6px 0}
li{margin-bottom:4px}
code{background:#0d0d14;padding:2px 6px;border-radius:4px;font-size:12px;color:#00d4ff}
pre{background:#050508;border:1px solid #1a1a2e;border-radius:8px;padding:16px;
  overflow-x:auto;font-size:12px;line-height:1.6;margin:12px 0}
hr{border:none;border-top:1px solid #1a1a2e;margin:20px 0}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:12px}
th{text-align:left;padding:10px 12px;background:#0d0d14;color:#00d4ff;
  border:1px solid #1a1a2e;font-size:11px;letter-spacing:1px;text-transform:uppercase}
td{padding:8px 12px;border:1px solid #1a1a2e;color:#bbb}
tr:hover td{background:#0a0a14}
strong{color:#e0e0e0}
em{color:#888}
"""


def _wrap_cyber(body: str, title: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>xHAL2049 — {title}</title><style>{_CYBER_CSS}</style></head><body>
<div id="grid"></div><a class="back" href="/">← VOLTAR</a>
<div class="wrap">{body}</div></body></html>"""


def _md_to_html(md: str) -> str:
    """Minimal markdown → HTML (no external deps)."""
    import re
    lines = md.split("\n")
    out = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("")
            continue
        # Headers
        if stripped.startswith("#### "):
            out.append(f"<h4>{stripped[5:]}</h4>")
        elif stripped.startswith("### "):
            out.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1 style='font-size:20px;color:#00d4ff'>{stripped[2:]}</h1>")
        elif stripped.startswith("---"):
            out.append("<hr>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = stripped[2:]
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            item = re.sub(r"\*(.+?)\*", r"<em>\1</em>", item)
            out.append(f"<li>{item}</li>")
        elif re.match(r"^\d+\.\s", stripped):
            item = re.sub(r"^\d+\.\s+", "", stripped)
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            out.append(f"<li>{item}</li>")
        elif stripped.startswith("|"):
            # Table row — handled separately
            out.append(f"<tr>{''.join(f'<td>{c.strip()}</td>' for c in stripped.split('|')[1:-1])}</tr>")
        else:
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
            text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
            out.append(f"<p>{text}</p>")
    if in_list:
        out.append("</ul>")
    # Wrap table rows
    result = "\n".join(out)
    result = re.sub(r"(<tr>.*?</tr>(\n?)*)+", lambda m: f"<table>{m.group(0)}</table>", result)
    return result


def _render_cyberpunk_skill(md: str, filename: str) -> str:
    body = f"""<div class="header">
  <h1>SKILL</h1>
  <div class="meta">{filename}</div>
</div>
{_md_to_html(md)}"""
    return _wrap_cyber(body, f"Skill — {filename}")


def _render_cyberpunk_summary(md: str, run_data: dict | None) -> str:
    # Parse stats from run_data
    stats_html = ""
    if run_data:
        total = run_data.get("total_files", 0)
        ok = run_data.get("successful", 0)
        sops = run_data.get("total_sops", 0)
        prins = run_data.get("total_principles", 0)
        stats_html = f"""<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0">
  <div style="background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;padding:16px;text-align:center">
    <div style="font-size:28px;color:#00d4ff;font-family:Orbitron">{total}</div>
    <div style="font-size:10px;color:#555;letter-spacing:1px;margin-top:4px">FILES</div>
  </div>
  <div style="background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;padding:16px;text-align:center">
    <div style="font-size:28px;color:#00ff88;font-family:Orbitron">{ok}</div>
    <div style="font-size:10px;color:#555;letter-spacing:1px;margin-top:4px">SUCCESS</div>
  </div>
  <div style="background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;padding:16px;text-align:center">
    <div style="font-size:28px;color:#ff0080;font-family:Orbitron">{sops}</div>
    <div style="font-size:10px;color:#555;letter-spacing:1px;margin-top:4px">SOPS</div>
  </div>
  <div style="background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;padding:16px;text-align:center">
    <div style="font-size:28px;color:#7b2ff7;font-family:Orbitron">{prins}</div>
    <div style="font-size:10px;color:#555;letter-spacing:1px;margin-top:4px">PRINCIPLES</div>
  </div>
</div>"""

    # Parse per-file results from run_data
    files_html = ""
    if run_data and run_data.get("results"):
        rows = ""
        for r in run_data["results"]:
            status_color = "#00ff88" if r.get("success") else "#ff0080"
            rows += f"""<tr>
  <td style="color:#e0e0e0">{r.get('filename','')}</td>
  <td style="color:{status_color}">{'OK' if r.get('success') else 'FAILED'}</td>
  <td>{r.get('sops_count',0)}</td>
  <td>{r.get('principles_count',0)}</td>
  <td>{r.get('response_chars',0):,}</td>
  <td>{r.get('elapsed',0):.1f}s</td>
</tr>"""
        files_html = f"""<h2>PER-FILE RESULTS</h2>
<table><thead><tr><th>FILE</th><th>STATUS</th><th>SOPS</th><th>PRINCIPLES</th><th>CHARS</th><th>TIME</th></tr></thead>
<tbody>{rows}</tbody></table>"""

    body = f"""<div class="header">
  <h1>EXECUTION REPORT</h1>
  <div class="meta">batch compilation summary</div>
</div>
{stats_html}
{files_html}
<h2>RAW LOG</h2>
<pre>{md}</pre>"""
    return _wrap_cyber(body, "Execution Report")


def _render_cyberpunk_sf(sf: dict) -> str:
    nodes = sf.get("nodes", [])
    edges = sf.get("edges", [])

    # Group nodes by type
    groups = {}
    for n in nodes:
        t = n.get("type", "unknown")
        groups.setdefault(t, []).append(n)

    type_colors = {
        "concept": "#00ff88", "principle": "#ff0080",
        "sop": "#7b2ff7", "reference": "#ffaa00",
    }
    type_icons = {
        "concept": "◆", "principle": "●",
        "sop": "■", "reference": "▲",
    }

    groups_html = ""
    for ntype, nodes_in_group in sorted(groups.items()):
        color = type_colors.get(ntype, "#888")
        icon = type_icons.get(ntype, "•")
        items = ""
        for n in nodes_in_group:
            label = n.get("term") or n.get("statement", "")[:80] or n.get("name", n.get("id", ""))
            definition = n.get("definition") or n.get("statement", "") or n.get("when_to_use", "")
            epistemic = n.get("epistemic_status", "")
            badge = f'<span style="color:{color};font-size:10px;border:1px solid {color}33;padding:1px 6px;border-radius:4px;margin-left:8px">{epistemic}</span>' if epistemic else ""
            items += f"""<div style="padding:10px 14px;border-bottom:1px solid #111;cursor:pointer" onmouseover="this.style.background='#0a0a14'" onmouseout="this.style.background='transparent'">
  <div style="color:{color};font-size:13px">{icon} {label}{badge}</div>
  <div style="font-size:11px;color:#666;margin-top:4px">{definition[:120]}{'...' if len(definition)>120 else ''}</div>
</div>"""
        groups_html += f"""<div style="margin:20px 0">
  <h2 style="color:{color}">{ntype.upper()}S <span style="font-size:11px;color:#555">({len(nodes_in_group)})</span></h2>
  <div style="background:#0a0a10;border:1px solid #1a1a2e;border-radius:8px;overflow:hidden">{items}</div>
</div>"""

    # Edges summary
    edges_html = ""
    if edges:
        edge_rows = ""
        for e in edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            etype = e.get("type", "")
            inferred = "dashed" if e.get("inferred") else "solid"
            edge_rows += f"<tr><td>{src}</td><td style='color:#00d4ff'>{etype}</td><td>{tgt}</td><td>{inferred}</td></tr>"
        edges_html = f"""<h2>EDGES <span style="font-size:11px;color:#555">({len(edges)})</span></h2>
<table><thead><tr><th>SOURCE</th><th>TYPE</th><th>TARGET</th><th>STYLE</th></tr></thead>
<tbody>{edge_rows}</tbody></table>"""

    body = f"""<div class="header">
  <h1>SEMANTIC FIELD</h1>
  <div class="meta">{sf.get('source_file','')} &nbsp;|&nbsp; {len(nodes)} nodes &nbsp;|&nbsp; {len(edges)} edges &nbsp;|&nbsp; {sf.get('built_at','')}</div>
</div>
{groups_html}
{edges_html}"""
    return _wrap_cyber(body, f"Semantic Field — {sf.get('source_file','')}")


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

        elif path == "/teach":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_TEACH_HTML.encode())

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
        compilation = session.output_dir / "compilation"
        if not compilation.exists():
            self.send_response(404)
            self.end_headers()
            return
        md_files = [f for f in compilation.glob("*.md")
                    if "semantic_field" not in f.name
                    and "batch_summary" not in f.name]
        if not md_files:
            self.send_response(404)
            self.end_headers()
            return
        md = md_files[0].read_text(encoding="utf-8")
        html = _render_cyberpunk_skill(md, md_files[0].name)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_graph(self, sid: str):
        session = _sessions.get(sid)
        if not session or not session.output_dir:
            self.send_response(404)
            self.end_headers()
            return
        compilation = session.output_dir / "compilation"
        if not compilation.exists():
            self.send_response(404)
            self.end_headers()
            return
        sf_files = list(compilation.glob("*semantic_field*.html"))
        if sf_files:
            self._serve_file(sf_files[0], "text/html; charset=utf-8")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Grafo não disponível</h3>".encode())

    def _serve_summary(self, sid: str):
        session = _sessions.get(sid)
        if not session or not session.output_dir:
            self.send_response(404)
            self.end_headers()
            return
        compilation = session.output_dir / "compilation"
        if not compilation.exists():
            self.send_response(404)
            self.end_headers()
            return
        summary_files = list(compilation.glob("*batch_summary*.md"))
        run_files = list(compilation.glob("*run*.json"))
        if summary_files:
            md = summary_files[0].read_text(encoding="utf-8")
            run_data = None
            if run_files:
                try:
                    run_data = json.loads(run_files[0].read_text(encoding="utf-8"))
                except Exception:
                    pass
            html = _render_cyberpunk_summary(md, run_data)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
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
        if not compilation.exists():
            self.send_response(404)
            self.end_headers()
            return
        sf_files = list(compilation.glob("*semantic_field*.json"))
        if sf_files:
            try:
                sf_data = json.loads(sf_files[0].read_text(encoding="utf-8"))
                html = _render_cyberpunk_sf(sf_data)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h3>Erro ao renderizar: {e}</h3><pre>{sf_files[0].read_text(encoding='utf-8')[:2000]}</pre>".encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Semantic Field não disponível</h3>".encode())
        # Find semantic_field.json by pattern
        sf_files = list(compilation.glob("*semantic_field*.json"))
        if sf_files:
            self._serve_file(sf_files[0], "application/json")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Semantic Field não disponível</h3><p>Sem dados de semantic field nesta sessão.</p>".encode())

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

        if self.path == "/api/teach/start":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                sf_path = data.get("sf_path", "")
                if not sf_path or not os.path.exists(sf_path):
                    resp = json.dumps({"ok": False, "error": "SF not found"})
                else:
                    sf = json.loads(Path(sf_path).read_text(encoding="utf-8"))
                    sid = uuid.uuid4().hex[:8]
                    _teach_sessions[sid] = {
                        "engine": None,
                        "sf": sf,
                        "history": [],
                        "sf_path": sf_path,
                    }
                    resp = json.dumps({"ok": True, "session_id": sid})
            except Exception as e:
                resp = json.dumps({"ok": False, "error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.encode())
            return

        if self.path == "/api/teach/respond":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                sid = data.get("session_id", "")
                user_input = data.get("response", "")
                ts = _teach_sessions.get(sid)
                if not ts:
                    resp = json.dumps({"ok": False, "error": "Session not found"})
                else:
                    if ts["engine"] is None:
                        from chavruta.engine import ChavrutaEngine
                        ts["engine"] = ChavrutaEngine(ts["sf"])
                    result = ts["engine"].process(user_input)
                    ts["history"].append({
                        "user": user_input[:200],
                        "challenge": result["challenge"],
                        "depth": result["depth"],
                        "depth_bar": result["depth_bar"],
                        "depth_label": result["depth_label"],
                        "is_contradiction": result["is_contradiction"],
                        "match_layer": result["match_layer"],
                    })
                    resp = json.dumps({
                        "ok": True,
                        "challenge": result["challenge"],
                        "depth": result["depth"],
                        "depth_bar": result["depth_bar"],
                        "depth_label": result["depth_label"],
                        "is_contradiction": result["is_contradiction"],
                        "match_layer": result["match_layer"],
                        "max_depth_seen": result["max_depth_seen"],
                        "matched_node": result.get("matched_node", {}).get("term") if result.get("matched_node") else None,
                    })
            except Exception as e:
                resp = json.dumps({"ok": False, "error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp.encode())
            return

        if self.path == "/api/teach/sessions":
            # List available SF files from previous compilations
            sessions = []
            upload_dir = Path(UPLOAD_DIR)
            for d in sorted(upload_dir.iterdir()):
                if not d.is_dir() or d.name.startswith("_"):
                    continue
                compilation = d / "compilation"
                sf_files = list(compilation.glob("*semantic_field*.json")) if compilation.exists() else []
                if sf_files:
                    md_files = [f for f in compilation.glob("*.md")
                                if "semantic_field" not in f.name and "batch_summary" not in f.name]
                    label = md_files[0].stem if md_files else d.name
                    sessions.append({
                        "id": d.name,
                        "label": label,
                        "sf_path": str(sf_files[0]),
                    })
            resp = json.dumps(sessions)
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
