"""HTML/CSS/JS templates for xHAL2049 Web Console."""

def html_page() -> str:
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
  <div style="position:absolute;top:16px;right:24px;display:flex;gap:16px;align-items:center">
    <a href="/teach" target="_blank" style="color:#00d4ff;text-decoration:none;font-size:12px;letter-spacing:1px" onmouseover="this.style.color='#7b2ff7'" onmouseout="this.style.color='#00d4ff'">⚔️ TEACH MODE</a>
    <a href="#historySection" onclick="document.getElementById('historySection').scrollIntoView({behavior:'smooth'})" style="color:#888;text-decoration:none;font-size:12px;letter-spacing:1px" onmouseover="this.style.color='#00d4ff'" onmouseout="this.style.color='#888'">📜 HISTÓRICO</a>
    <a href="/settings" style="color:#555;text-decoration:none;font-size:12px" onmouseover="this.style.color='#00d4ff'" onmouseout="this.style.color='#555'">⚙ CONFIG</a>
  </div>
</div>

<div class="main">
  <div class="upload-zone" id="dropZone">
    <div class="icon">📁</div>
    <div class="label">Arraste arquivos aqui ou <b>clique para selecionar</b></div>
    <div class="label" style="margin-top:6px;font-size:11px;color:#444">PDF, EPUB, DOCX, TXT, SRT, MD, MP3, WAV, MP4 — ou URL do YouTube</div>
    <input type="file" id="fileInput" multiple accept=".pdf,.epub,.docx,.txt,.srt,.vtt,.md,.mp3,.wav,.mp4">
  </div>
  <div class="files-list" id="filesList"></div>

  <div class="actions">
    <button class="btn btn-primary" id="btnStart" disabled>EXTRACT KNOWLEDGE</button>
    <button class="btn btn-danger" id="btnCancel" style="display:none">CANCEL</button>
    <div class="status" id="status"><span class="dot dot-idle"></span>Aguardando arquivos</div>
  </div>

  <div class="console" id="console">
    <div class="line dim">[xHAL2049 Kernel v2.5 initialized — ready]</div>
  </div>

  <div class="results" id="results" style="display:none">
    <div style="font-size:11px;color:#888;letter-spacing:1px;margin-bottom:10px">RESULTADOS DA EXTRAÇÃO ATUAL:</div>
    <div class="results-btns">
      <a class="btn-result" id="btnSkill" target="_blank">📄 Skill Markdown</a>
      <a class="btn-result" id="btnGraph" target="_blank">🕸 Grafo Hie</a>
      <a class="btn-result" id="btnSummary" target="_blank">📊 Execution Report</a>
      <a class="btn-result" id="btnSF" target="_blank">🌌 Semantic Field (JSON)</a>
      <a class="btn-result" id="btnZip" target="_blank" style="border-color:#00ff88;color:#00ff88">📦 Baixar Tudo (.ZIP)</a>
      <a class="btn-result" id="btnTeach" target="_blank" style="border-color:#7b2ff7;color:#00d4ff">⚔️ Teach Mode (Debate Socrático)</a>
    </div>
  </div>

  <div class="results" id="historySection" style="margin-top:24px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-size:12px;color:#888;letter-spacing:1px;font-weight:bold">📜 HISTÓRICO DE EXTRAÇÕES</div>
      <button onclick="loadHistory()" style="background:transparent;border:1px solid #333;color:#888;padding:4px 10px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:11px">↺ Atualizar</button>
    </div>
    <div id="historyList" style="display:flex;flex-direction:column;gap:10px">
      <div style="font-size:11px;color:#555">Carregando histórico...</div>
    </div>
  </div>
</div>

<div class="footer">
  xHAL2049 SOP Extractor — local execution server — <span id="apiKeyStatus"></span>
</div>

<script>
let selectedFiles = [];
let currentSid = null;
let evtSource = null;

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const filesList = document.getElementById('filesList');
const btnStart = document.getElementById('btnStart');
const btnCancel = document.getElementById('btnCancel');
const consoleEl = document.getElementById('console');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', e => addFiles(e.target.files));

function addFiles(files) {
  for (let f of files) selectedFiles.push(f);
  renderFiles();
}

function renderFiles() {
  filesList.innerHTML = selectedFiles.map((f, i) =>
    `<span class="file">${f.name} <span style="cursor:pointer;color:#ff4488" onclick="removeFile(${i})">×</span></span>`
  ).join('');
  btnStart.disabled = selectedFiles.length === 0;
}

function removeFile(i) {
  selectedFiles.splice(i, 1);
  renderFiles();
}

btnStart.addEventListener('click', async () => {
  if (selectedFiles.length === 0) return;
  btnStart.disabled = true;
  setStatus('running', 'Enviando arquivos...');
  resultsEl.style.display = 'none';

  const formData = new FormData();
  for (let f of selectedFiles) formData.append('file', f);

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();
    currentSid = data.session_id;
    startSSE(currentSid);
  } catch(e) {
    log('err', 'Erro no upload: ' + e.message);
    setStatus('error', 'Falha no upload');
    btnStart.disabled = false;
  }
});

function startSSE(sid) {
  setStatus('running', 'Processando extração...');
  btnCancel.style.display = 'inline-block';
  log('info', `Iniciando sessão [${sid}]...`);

  evtSource = new EventSource(`/progress/${sid}`);
  evtSource.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'line') {
      log(msg.level || 'dim', msg.text);
    } else if (msg.type === 'done') {
      evtSource.close();
      setStatus('done', 'Concluído com ' + msg.message);
      btnCancel.style.display = 'none';
      btnStart.disabled = false;
      showResults(sid);
    } else if (msg.type === 'error') {
      evtSource.close();
      log('err', 'Erro no processamento: ' + msg.message);
      setStatus('error', 'Falha no processamento');
      btnCancel.style.display = 'none';
      btnStart.disabled = false;
    }
  };
  evtSource.onerror = () => {
    log('err', 'Conexão perdida com o servidor.');
    setStatus('error', 'Erro de conexão');
    evtSource.close();
    btnCancel.style.display = 'none';
    btnStart.disabled = false;
  };
}

btnCancel.addEventListener('click', async () => {
  if (currentSid) {
    await fetch(`/cancel/${currentSid}`, { method: 'POST' });
    if (evtSource) evtSource.close();
    log('warn', 'Processo cancelado pelo usuário.');
    setStatus('idle', 'Cancelado');
    btnCancel.style.display = 'none';
    btnStart.disabled = false;
  }
});

function showResults(sid) {
  resultsEl.style.display = 'block';
  document.getElementById('btnSkill').href = `/results/${sid}/skill`;
  document.getElementById('btnGraph').href = `/results/${sid}/graph`;
  document.getElementById('btnSummary').href = `/results/${sid}/summary`;
  document.getElementById('btnSF').href = `/results/${sid}/sf`;
  document.getElementById('btnZip').href = `/results/${sid}/zip`;
  document.getElementById('btnTeach').href = `/teach?session=${sid}`;
  loadHistory();
}

async function loadHistory() {
  const historyList = document.getElementById('historyList');
  if (!historyList) return;
  try {
    const res = await fetch('/api/history');
    const items = await res.json();
    if (!items || items.length === 0) {
      historyList.innerHTML = '<div style="font-size:11px;color:#555">Nenhuma extração anterior encontrada.</div>';
      return;
    }
    historyList.innerHTML = items.map(item => `
      <div style="background:#080810;border:1px solid #1a1a2e;border-radius:8px;padding:12px 16px;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px">
        <div>
          <div style="font-size:13px;font-weight:bold;color:#e0e0e0">${escapeHtml(item.filename)}</div>
          <div style="font-size:11px;color:#666;margin-top:4px">
            📅 ${item.created_at} &nbsp;|&nbsp; 📋 ${item.sops} SOPs &nbsp;•&nbsp; 💡 ${item.principles} Princípios &nbsp;•&nbsp; 🧠 ${item.concepts} Conceitos
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <a class="btn-result" style="padding:4px 10px;font-size:11px" href="/results/${item.sid}/skill" target="_blank">📄 Skill</a>
          <a class="btn-result" style="padding:4px 10px;font-size:11px" href="/results/${item.sid}/graph" target="_blank">🕸 Grafo</a>
          <a class="btn-result" style="padding:4px 10px;font-size:11px" href="/results/${item.sid}/summary" target="_blank">📊 Report</a>
          <a class="btn-result" style="padding:4px 10px;font-size:11px" href="/results/${item.sid}/sf" target="_blank">🌌 JSON</a>
          <a class="btn-result" style="padding:4px 10px;font-size:11px;border-color:#00ff88;color:#00ff88" href="/results/${item.sid}/zip" target="_blank">📦 .ZIP</a>
          <a class="btn-result" style="padding:4px 10px;font-size:11px;border-color:#7b2ff7;color:#00d4ff" href="/teach?session=${item.sid}" target="_blank">⚔️ Teach</a>
        </div>
      </div>
    `).join('');
  } catch(e) {
    historyList.innerHTML = '<div style="font-size:11px;color:#ff4444">Erro ao carregar histórico.</div>';
  }
}
document.addEventListener('DOMContentLoaded', loadHistory);
loadHistory();

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
  const models = MODEL_PRESETS[name] || [];
  const el = document.getElementById('modelPresets');
  el.innerHTML = models.map(m =>
    `<span class="preset" onclick="document.getElementById('model').value='${m}'">${m}</span>`
  ).join('');
}

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
