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
</style>
</head>
<body>
<div class="banner">
  <h1>xHAL2049</h1>
  <div class="sub">SOP EXTRACTOR — KNOWLEDGE COMPILATION CONSOLE</div>
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
  </div>

  <div class="console" id="console"></div>
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
</body>
</html>"""


class Session:
    def __init__(self, sid: str, files: list[Path]):
        self.sid = sid
        self.files = files
        self.q: queue.Queue = queue.Queue()
        self.done = False
        self.error = None

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
        for f in session.files:
            session.emit("info", f"▸ Processando: {f.name}")
            cmd = [
                sys.executable, os.path.join(SCRIPTS_DIR, "run.py"),
                str(f), "--compile",
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=PROJECT_ROOT,
            )
            for line in proc.stdout:
                session.emit("info", line.rstrip())
            proc.wait()
            if proc.returncode != 0:
                session.emit("warn", f"⚠ {f.name} retornou exit code {proc.returncode}")
            else:
                session.emit("ok", f"✓ {f.name} concluído")

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

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
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
