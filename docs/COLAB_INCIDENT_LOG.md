
## Incident Log — Colab Ingestion Testing (QuantGuild, 2026-07-24)

### Incident C1: BatchedInferencePipeline required for batch_size
- **Symptom**: `WhisperModel.transcribe() got an unexpected keyword argument 'batch_size'`
- **Root cause**: `WhisperModel.transcribe()` does NOT accept `batch_size`. Must use `BatchedInferencePipeline(model=model)` wrapper.
- **Fix**: `from faster_whisper.transcribe import BatchedInferencePipeline` + `model = BatchedInferencePipeline(model=whisper_model)`
- **Notebook cell**: Transcription engine cell
- **Known since**: ses_070b0cbb2ffe (local code already fixed, Colab notebook missed it)

### Incident C2: deno required by yt-dlp 2026.x for YouTube
- **Symptom**: `WARNING: [youtube] No supported JavaScript runtime could be found. Only deno is enabled`
- **Root cause**: yt-dlp 2026.x requires a JavaScript runtime (deno) for YouTube's JS-based player verification. Previous yt-dlp versions bundled this or used a different approach.
- **Fix option 1**: Install deno to `/usr/local/bin/deno` (direct binary download from GitHub releases)
- **Fix option 2**: Pin yt-dlp to pre-2026 version (`pip install yt-dlp==2024.12.13`)
- **Colab-specific**: `curl | sh` installation may fail silently. Use direct binary download + unzip instead.
- **Notebook cell**: Install dependencies cell
- **Anti-pattern**: `curl -fsSL https://deno.land/install.sh | sh` with `shell=True` — subprocess env doesn't inherit PATH changes.

### Incident C3: Colab GPU quota exhaustion
- **Symptom**: "Nenhum back-end com GPU disponível"
- **Root cause**: Colab free tier has limited GPU quotas that expire after ~12-24h of usage.
- **Mitigation**: CPU fallback with `base` model (~2x realtime). Acceptable for pipeline testing.
- **Performance**: CPU base model: 8h20m content → ~4h processing. GPU T4 large-v3: → ~20min.

### Incident C4: HuggingFace unauthenticated warning
- **Symptom**: `Warning: You are sending unauthenticated requests to the HF Hub`
- **Root cause**: HuggingFace Hub rate limits for unauthenticated users.
- **Impact**: Cosmetic only — model downloads succeed. Can set `HF_TOKEN` env var for higher limits.
- **Severity**: Informational (not a blocker)

---

### Incident C2-fix: deno download URL fails in Colab
- **Symptom**: `CalledProcessError: curl -fsSL -o /tmp/deno.zip https://github.com/denoland/deno/releases/latest/download/deno-linux-x64.zip` → exit status 22
- **Root cause**: GitHub release URL for deno returns 404/redirect. `curl -f` treats HTTP errors as failures.
- **Final fix**: Pin yt-dlp to `2025.3.1` — last version that does NOT require deno for YouTube JS verification. Eliminates deno dependency entirely.
- **Decision**: For Colab notebooks, prefer pinned yt-dlp over runtime deno installation. Simpler, more reliable, no external binary downloads.
- **Severity**: Blocker (prevented all downloads)

### Incident C5: yt-dlp not found after pip install
- **Symptom**: `FileNotFoundError: [Errno 2] No such file or directory: 'yt-dlp'`
- **Root cause**: `pip install yt-dlp` installs to a path not on system PATH in Colab. `shutil.which('yt-dlp')` returns None.
- **Fix**: Use `python -m yt_dlp` instead of calling `yt-dlp` binary directly. Wraps all yt-dlp calls through `YTDLP_ARGS = ['-m', 'yt_dlp']`.
- **Severity**: Blocker (prevented all downloads)

### Incident C6: Notebook regression chain (C1→C2→C5)
- **Pattern**: Each fix introduced a new failure mode. Root cause: incremental patches without full rewrite.
- **Lesson**: When Colab notebook hits 3+ consecutive failures, do a COMPLETE REWRITE instead of patching. Colab environment differs from local venv in: PATH, pre-installed packages, permissions.
- **Decision**: All future Colab notebooks must use `python -m yt_dlp` (never bare binary), `BatchedInferencePipeline` wrapper, and GPU auto-detection.

### Incident C7: faster-whisper import fails after pip install
- **Symptom**: `ModuleNotFoundError: No module named 'faster_whisper'` despite cell 1 showing "Done"
- **Root cause**: `subprocess.run(..., capture_output=True)` silently swallows pip errors. Install fails but notebook continues.
- **Fix**: Verify import after install. If fails, retry without `capture_output` to show full error. Always add `try/except ImportError` block.
- **Severity**: Blocker (cell 3 crashes)
- **Pattern**: Colab's pre-installed packages can conflict with pip versions. Always verify critical imports after install.

### Incident C8: Stop patching, rewrite (meta-lesson)
- **7 consecutive failures** in a single Colab notebook session.
- **Root cause of all failures**: Over-engineering. Used subprocess, PATH detection, version pinning — all unnecessary in Colab.
- **Final fix**: `!pip install` for deps, `os.system()` for yt-dlp, no subprocess, no PATH hacking.
- **Lesson**: Colab notebooks should use Colab-native patterns (!magic, os.system). Porting local adapter code to Colab is the wrong approach — they're different environments.
- **Rule for future Colab notebooks**: 
  1. `!pip install` (not subprocess pip)
  2. `os.system()` or `!yt-dlp` for shell commands (not subprocess.run)
  3. No binary PATH detection (Colab has consistent paths)
  4. No version pinning unless explicitly tested on Colab
  5. Verify critical imports after install
  6. After 3 failures → full rewrite, not patch
