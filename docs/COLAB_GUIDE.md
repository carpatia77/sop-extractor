# Transcrição com GPU no Google Colab

Guia rápido para acelerar transcrições usando GPU gratuita.

---

## Por que usar GPU?

| Hardware | 20min vídeo | 52min vídeo |
|----------|-------------|-------------|
| CPU (Pentium) | ~8min | ~31min |
| GPU T4 (Colab) | ~1:10 | ~4:30 |

**Speedup:** ~7x mais rápido com GPU.

---

## Passos Rápidos

### 1. Abrir Colab

Acesse: [colab.research.google.com](https://colab.research.google.com)

### 2. Ativar GPU

**Runtime → Change runtime type → T4 GPU**

### 3. Rodar o notebook

Copie o notebook de `examples/colab_transcribe.ipynb` ou execute os comandos:

```python
# Instalar
!pip install -q faster-whisper yt-dlp

# Carregar modelo
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cuda", compute_type="int8")

# Transcrever
segments, info = model.transcribe("audio.mp3", batch_size=8)
```

### 4. Download

```python
from google.colab import files
files.download("transcript.srt")
```

---

## Limitações

| Item | Limite |
|------|--------|
| Sessão gratuita | 12h max, idle 90min |
| Armazenamento | ~100GB temporário |
| GPU | T4 (16GB VRAM) |
| Requer | Conta Google + internet |

---

## Custo

- **Gratuito:** Tier básico (sessões limitadas)
- **Pro ($10/mês):** Mais GPU hours, sem idle timeout

---

## Quando usar

- ✅ Vídeos longos (>30min) em CPU fraca
- ✅ Lotes de vídeos para processar rápido
- ✅ Sem GPU local
- ❌ Não usar para poucos vídeos curtos (overhead de setup)
