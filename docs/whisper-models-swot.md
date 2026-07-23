# SWOT — Modelos Open-Source de Transcrição (STT)

**Data:** 2026-07-22 | **Contexto:** Otimizar UX do módulo de ingestão (fase 0)

## Benchmark Atual (nosso hardware: CPU, Intel, sem GPU)

| Modelo | Duração Áudio | Tempo Real | Speed Ratio | RAM |
|--------|--------------|------------|-------------|-----|
| whisper base (atual) | 19:56 | ~20:16 | 0.87x | ~2.2GB |
| whisper tiny (teste) | 1:19 | ~0:06 | 13x | ~1GB |

## Comparativo dos Modelos Disponíveis

### 1. faster-whisper (ATUAL — SYSTRAN) ⭐ 24.5k★

| Aspecto | Detalhe |
|---------|---------|
| **O que é** | Reimplementação do Whisper usando CTranslate2 (backend de inferência) |
| **Velocidade** | 4x mais rápido que openai/whisper original |
| **Quantização** | Suporta int8 em CPU e GPU (reduce RAM 40-50%) |
| **Batch** | batch_size=8 reduz tempo em 3-4x (usa mais RAM) |
| **GPU** | CUDA 12 + cuDNN 9 |
| **CPU** | OpenVINO para Intel (faster-whisper + openvino) |

**SWOT:**

| | Positivo | Negativo |
|---|----------|----------|
| **Interno** | ✅ Já instalado, compatível com nosso código | ❌ CPU-only neste hardware (sem GPU) |
| | ✅ int8 quantization reduz RAM 40% | ❌ ctranslate2 warning chato em CPU |
| | ✅ Batch inference disponível | ❌ batch precisa de mais RAM |
| **Externo** | ✅ Maior comunidade STT (24.5k★) | ❌ Depende de ctranslate2 (C++ binding) |
| | ✅ Suporta todos os modelos Whisper | ❌ Atualização pode quebrar compatibilidade |

### 2. openai/whisper (ORIGINAL) ⭐ 105k★

| Aspecto | Detalhe |
|---------|---------|
| **O que é** | Implementação de referência da OpenAI |
| **Velocidade** | Referência (1x) — o mais lento |
| **RAM** | ~2.3GB (small), ~5GB (medium) |
| **Precisão** | Referência — baseline para comparação |

**SWOT:**

| | Positivo | Negativo |
|---|----------|----------|
| **Interno** | ✅ Mais documentado, fácil debug | ❌ 4x mais lento que faster-whisper |
| | ✅ PyTorch puro (sem C++ deps) | ❌ Mais RAM que faster-whisper |
| **Externo** | ✅ 105k★ — maior comunidade | ❌ Sem batch inference |
| | ✅ Suporte oficial OpenAI | ❌ Sem quantização int8 |

### 3. whisper.cpp ⭐ 38k★

| Aspecto | Detalhe |
|---------|---------|
| **O que é** | Port C++ do Whisper, otimizado para CPU |
| **Velocidade** | 3-4x mais rápido que openai/whisper em CPU |
| **RAM** | ~1GB (small) — menor de todos |
| **GPU** | Metal (macOS), CUDA, OpenCL |
| **Especial** | OpenVINO para Intel CPUs |

**SWOT:**

| | Positivo | Negativo |
|---|----------|----------|
| **Interno** | ✅ Mais rápido em CPU (nosso caso) | ❌ Binding Python menos maduro |
| | ✅ Menor RAM (~1GB vs ~2.3GB) | ❌ Precisa compilar ou instalar binário |
| | ✅ OpenVINO = otimização Intel | ❌ Não integra com faster-whisper API |
| **Externo** | ✅ Portável (Linux, macOS, Windows) | ❌ Não suporta batch inference |
| | ✅ 38k★ — comunidade ativa | ❌ Menos integrações Python |

### 4. whisper turbo (MODELO NOVO — OpenAI)

| Aspecto | Detalhe |
|---------|---------|
| **O que é** | Versão otimizada do large-v3 |
| **Parâmetros** | 809M (vs 1550M do large) |
| **Velocidade** | ~8x mais rápido que large |
| **VRAM** | ~6GB (GPU) |
| **Precisão** | Praticamente igual ao large |

**SWOT:**

| | Positivo | Negativo |
|---|----------|----------|
| **Interno** | ✅ Melhor qualidade que base com velocidade ok | ❌ Precisa de GPU para ser útil |
| | ✅ 809M params — sweet spot | ❌ ~6GB VRAM mínimo |
| **Externo** | ✅ Modelo mais recente da OpenAI | ❌ Não treinado para tradução |
| | ✅ Suportado por faster-whisper | ❌ Apenas multilingual (sem .en) |

### 5. distil-whisper (DISTILLED)

| Aspecto | Detalhe |
|---------|---------|
| **O que é** | Whisper destilado — mais rápido, menos parâmetros |
| **Velocidade** | ~2x mais rápido que large |
| **Precisão** | ~1-2% pior que large |
| **Especial** | Otimizado para batch processing |

**SWOT:**

| | Positivo | Negativo |
|---|----------|----------|
| **Interno** | ✅ Bom para batch de vídeos | ❌ Precisa de GPU para batch |
| | ✅ Compatível com faster-whisper | ❌ English-only para best performance |
| **Externo** | ✅ Ideal para processamento em lote | ❌ Menos suporte que whisper base |
| | ✅ Hugging Face ativo | ❌ Precisa de Fine-tuning para PT-BR |

### 6. Faster-whisper + batch_size=8 (FEATURE)

| Aspecto | Detalhe |
|---------|---------|
| **O que é** | Mesmo modelo, processamento em lote |
| **Velocidade** | 3-4x mais rápido que single |
| **RAM** | ~4.2GB (small) vs ~2.3GB (single) |
| **CPU** | Funciona em CPU com batch=8 |

**SWOT:**

| | Positivo | Negativo |
|---|----------|----------|
| **Interno** | ✅ Não precisa mudar modelo | ❌ 2x mais RAM |
| | ✅ 3-4x mais rápido com batch=8 | ❌ Primeira chamada mais lenta |
| **Externo** | ✅ Feature nativa do faster-whisper | ❌ Pode dar OOM em RAM limitada |

## Recomendação para o nosso caso

### Cenário: CPU-only, 8GB RAM, vídeos 20-60min

| Opção | Ganho | Custo | Viável? |
|-------|-------|-------|---------|
| **faster-whisper int8** | ~1.5x mais rápido, 40% menos RAM | Zero (feature nativa) | ✅ IMEDIATO |
| **faster-whisper batch=8** | ~3x mais rápido | +2GB RAM | ✅ POSSÍVEL |
| **whisper.cpp + OpenVINO** | ~2-3x mais rápido em CPU | Setup adicional | ✅ MÉDIO |
| **whisper turbo (GPU)** | ~8x mais rápido | Precisa GPU 6GB | ❌ SEM GPU |
| **whisper tiny** | ~10x mais rápido | Perde precisão | ⚠️ SOFRE QUALIDADE |

### Ação Imediata (sem trocar de modelo)

```python
# Mudar de float32 para int8 — ganho grátis
model = WhisperModel("base", device="cpu", compute_type="int8")

# + batch inference — ganho 3x
from faster_whisper import BatchedInferencePipeline
batched = BatchedInferencePipeline(model=model)
segments, info = batched.transcribe(audio_path, batch_size=8)
```

**Estimativa com int8 + batch=8:** 20min de vídeo → ~5-7min (vs 20min atual)

### Ação Futura (quando tiver GPU)

Trocar para `whisper turbo` ou `large-v3` em GPU — qualidade near-perfect, 8x mais rápido.
