# Incidentes na Geração de Script Colab — Ground Truth

**Data:** 2026-07-23
**Contexto:** Validação da Fase 0 — geração automática de notebooks Colab para transcrição de vídeo com GPU

---

## Resumo

Durante a implementação do sistema de geração automática de notebooks Colab (`sopx/ingest/colab.py`), foram encontrados **5 incidentes** que causaram falhas na execução dos notebooks gerados. Este documentoserve como **ground truth** para o motor de geração de código, documentando os padrões que DEVEM ser seguidos e os que DEVEM ser evitados.

---

## Incidente 1: Parâmetro `batch_size` em API incorreta

**Data:** 2026-07-23 19:40
**Severidade:** Alta
**Status:** Resolvido

### Erro
```python
TypeError: WhisperModel.transcribe() got an unexpected keyword argument 'batch_size'
```

### Causa
Uso de `batch_size` diretamente no `WhisperModel.transcribe()`. O parâmetro `batch_size` é exclusivo do `BatchedInferencePipeline.transcribe()`.

### Código Incorreto
```python
from faster_whisper import WhisperModel

model = WhisperModel("base", device="cuda", compute_type="int8")
segments, info = model.transcribe(audio_file, batch_size=16, beam_size=5)  # ❌ ERRO
```

### Código Correto
```python
from faster_whisper import WhisperModel, BatchedInferencePipeline

model = WhisperModel("base", device="cuda", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)
segments, info = batched_model.transcribe(audio_file, batch_size=16, beam_size=5)  # ✅ OK
```

### Regra
> Ao usar `batch_size`, SEMPRE usar `BatchedInferencePipeline`, nunca `WhisperModel` diretamente.

---

## Incidente 2: Mistura de f-string com .format()

**Data:** 2026-07-23 20:00
**Severidade:** Alta
**Status:** Resolvido

### Erro
```python
SyntaxError: f-string: valid expression required before '}'
```

### Causa
Mistura de sintaxe f-string com `.format()` na mesma string.

### Código Incorreto
```python
print(f'{} vídeos para transcrever'.format(len(VIDEO_IDS)))  # ❌ ERRO
```

### Código Correto
```python
print(f'{len(VIDEO_IDS)} vídeos para transcrever')  # ✅ OK
```

### Regra
> NUNCA misturar f-string com `.format()`. Usar APENAS uma das duas abordagens.

---

## Incidente 3: Indentação incorreta em bloco try/except

**Data:** 2026-07-23 20:15
**Severidade:** Alta
**Status:** Resolvido

### Erro
```python
SyntaxError: expected 'except' or 'finally' block
```

### Causa
Código após definição de função interna (`def ts(s):`) ficou fora do bloco `try` por falta de indentação.

### Código Incorreto
```python
def transcribe(video_id):
    try:
        # ... código ...
        def ts(s):
            h, m, sec = int(s//3600), int((s%3600)//60), int(s%60)
            ms = round((s-int(s))*1000)
            return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'
    # ❌ FALTA INDENTAÇÃO - código fora do try
    srt = '\n'.join(...)
    return meta

    except Exception as e:  # ❌ ERRO: bloco try incompleto
        ...
```

### Código Correto
```python
def transcribe(video_id):
    try:
        # ... código ...
        def ts(s):
            h, m, sec = int(s//3600), int((s%3600)//60), int(s%60)
            ms = round((s-int(s))*1000)
            return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'

        srt = '\n'.join(...)  # ✅ DENTRO do try
        return meta

    except Exception as e:
        ...
```

### Regra
> Todo código dentro de `try` DEVE ter indentação consistente. Funções internas DEVEM ser definidas ANTES do código que as usa, ambas dentro do mesmo bloco.

---

## Incidente 4: Erros de download escondidos

**Data:** 2026-07-23 20:30
**Severidade:** Média
**Status:** Resolvido

### Erro
Output vazio na pasta `output/` — transcrição retornava 0 vídeos processados.

### Causa
Uso de `os.system()` com `2>/dev/null` que esconde todos os erros do yt-dlp.

### Código Incorreto
```python
os.system(f'yt-dlp -x --audio-format mp3 -o temp_audio.%(ext)s {url} 2>/dev/null')  # ❌ ERROS OCULTOS

audio = next(Path('.').glob('temp_audio.*'), None)
if not audio:
    print('Erro no download')  # Sem detalhes do que aconteceu
    return None
```

### Código Correto
```python
import subprocess

result = subprocess.run(
    ['yt-dlp', '-x', '--audio-format', 'mp3', '-o', 'temp_audio.%(ext)s', url],
    capture_output=True, text=True, timeout=300
)

if result.returncode != 0:
    print(f'Erro no download:')
    print(f'  {result.stderr[:500]}')  # ✅ MOSTRA ERRO DETALHADO
    return None

audio = next(Path('.').glob('temp_audio.*'), None)
if not audio:
    print('Arquivo de áudio não encontrado')
    return None

print(f'Áudio: {audio.name} ({audio.stat().st_size / 1024 / 1024:.1f} MB)')  # ✅ VERIFICA TAMANHO
```

### Regra
> NUNCA usar `os.system()` com `2>/dev/null` para comandos que podem falhar. SEMPRE usar `subprocess.run()` com `capture_output=True` para capturar erros.

---

## Incidente 5: ZIP criado antes dos arquivos

**Data:** 2026-07-23 20:45
**Severidade:** Média
**Status:** Resolvido

### Erro
ZIP vazio ou com arquivos incompletos.

### Causa
Código de download executado sem verificar se a transcrição completou.

### Código Incorreto
```python
# Célula 6: Processar
for vid in VIDEO_IDS:
    r = transcribe(vid)
    if r:
        results.append(r)

# Célula 7: Download (executa IMEDIATAMENTE)
shutil.make_archive('transcriptions', 'zip', 'output')  # ❌ PODE RODAR ANTES DE TERMINAR
files.download('transcriptions.zip')
```

### Código Correto
```python
# Célula 6: Processar
for vid in VIDEO_IDS:
    r = transcribe(vid)
    if r:
        results.append(r)

# Célula 7: Download (com verificação)
output_dir = Path('output')
if not output_dir.exists() or not any(output_dir.iterdir()):
    print('Nenhum resultado encontrado. Execute as células anteriores!')
else:
    # Listar arquivos
    print('Arquivos gerados:')
    for f in output_dir.rglob('*'):
        if f.is_file():
            print(f'  {f}')

    # Criar ZIP
    shutil.make_archive('transcriptions', 'zip', 'output')
    zip_path = Path('transcriptions.zip')
    print(f'ZIP criado: {zip_path.stat().st_size / 1024:.1f} KB')

    # Baixar
    files.download('transcriptions.zip')
```

### Regra
> ANTES de criar ZIP ou fazer download, SEMPRE verificar se os arquivos existem e não estão vazios.

---

## Padrões de Geração de Notebook

### Importações obrigatórias
```python
import time
import json
import os
import subprocess
from pathlib import Path
from faster_whisper import WhisperModel, BatchedInferencePipeline
```

### Carregamento do modelo
```python
model = WhisperModel("base", device="cuda", compute_type="int8")
batched_model = BatchedInferencePipeline(model=model)
```

### Download de áudio
```python
result = subprocess.run(
    ['yt-dlp', '-x', '--audio-format', 'mp3', '-o', 'temp_audio.%(ext)s', url],
    capture_output=True, text=True, timeout=300
)
if result.returncode != 0:
    print(f'Erro: {result.stderr[:500]}')
    return None
```

### Transcrição
```python
segments, info = batched_model.transcribe(str(audio), batch_size=16, beam_size=5)
segs = list(segments)
```

### Geração de SRT
```python
def ts(s):
    h, m, sec = int(s//3600), int((s%3600)//60), int(s%60)
    ms = round((s-int(s))*1000)
    return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'

srt_lines = []
for i, seg in enumerate(segs, 1):
    srt_lines.append(str(i))
    srt_lines.append(f'{ts(seg.start)} --> {ts(seg.end)}')
    srt_lines.append(seg.text.strip())
    srt_lines.append('')
srt = '\n'.join(srt_lines)
```

### Download de resultados
```python
output_dir = Path('output')
if not output_dir.exists() or not any(output_dir.iterdir()):
    print('Nenhum resultado encontrado!')
else:
    shutil.make_archive('transcriptions', 'zip', 'output')
    files.download('transcriptions.zip')
```

---

## Checklist de Validação

Antes de gerar um notebook Colab, verificar:

- [ ] `BatchedInferencePipeline` é usado para `batch_size`
- [ ] F-strings NÃO misturam com `.format()`
- [ ] Blocos `try/except` têm indentação consistente
- [ ] Downloads usam `subprocess.run()` com `capture_output=True`
- [ ] Erros são mostrados ao usuário (não escondidos)
- [ ] ZIP é criado APÓS verificação de existência de arquivos
- [ ] Todas as células compilam sem erros de sintaxe
- [ ] Imports estão na primeira célula de código

---

## Referência

- **Arquivo:** `sopx/ingest/colab.py`
- **CLI:** `scripts/ingest.py` (flag `--gpu`)
- **Testes:** `tests/test_hardware.py` (25 testes)
- **Commits:** `347b9bd`, `63cadc7`, `17ac3ce`
