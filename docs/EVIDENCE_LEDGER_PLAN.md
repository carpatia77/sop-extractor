# Evidence Ledger — Fechamento do Issue 2

## Contexto

O auditor identificou que "Evidence Ledger ✅ 100%" era falso. O campo `evidence_id` existe mas e posicional (`#principle:3`), nao uma ancora real. O Evidence Ledger real precisa de: entry_id, locator, excerpt_hash, evidence_text. Estes campos sao prerequisito para a ancora #3 do tiebreaker Depth-6/Drift (Fase D do AUDITOR_FIXES_PLAN.md).

---

## O que ja existe (dados disponiveis no pipeline)

| Campo | Fonte | Status |
|-------|-------|--------|
| `claim` | `principle.statement` | ✅ Disponivel |
| `source_file` | `filepath` (compilation) | ✅ Disponivel |
| `source_sha256` | `sha256_file(filepath)` | ✅ Disponivel |
| `upload_date` | `metadata.json` via `read_source_metadata()` | ✅ Disponivel |
| `epistemic_status` | `principle.epistemic_status` | ✅ Disponivel |
| `refutation` | `refutation_chain.py` output | ✅ Disponivel |
| `locator` | SRT timestamps (cues com `00:12:34 --> 00:13:02`) | ❌ Precisa extrair |
| `excerpt_hash` | Hash do trecho-fonte do claim | ❌ Precisa calcular |
| `evidence_text` | Trecho literal da fonte que suporta o claim | ❌ Precisa extrair |
| `entry_id` | UUID deterministico (content-based) | ❌ Precisa gerar |

---

## Algoritmo de extração de locator + evidence_text

O compile.py ja le o source_content (texto puro, SRT ja stripped). Mas o SRT original tem timestamps. A solucao:

1. **Para fontes SRT**: Ler o SRT original (antes de strip_srt) e mapear cada trecho de texto para seu timestamp. Quando o LLM gera um principle com `evidence` (trecho citado), buscar o trecho no SRT e retornar o timestamp do cue correspondente.

2. **Para fontes TXT/MD**: O locator e o numero da linha ou paragrafo onde o trecho aparece.

### Funcao central: `extract_locator()`

```python
def extract_locator(claim: str, evidence: str, source_path: str) -> dict:
    """Extrai locator e evidence_text de uma fonte.
    
    Para SRT: retorna timestamp do cue mais proximo do evidence text.
    Para TXT/MD: retorna numero da linha.
    """
    # 1. Se evidence esta vazio, retorna vazio
    # 2. Ler fonte original (SRT com timestamps ou TXT puro)
    # 3. Buscar evidence no texto
    # 4. Retornar {locator, excerpt_hash, evidence_text}
```

### Para SRT: parsing de cues com timestamps

```python
_SRT_CUE_RE = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"
    r"(.+?)(?=\n\n|\n\d+\s*\n|\Z)",
    re.DOTALL,
)

def parse_srt_with_timestamps(srt_text: str) -> list[dict]:
    """Retorna lista de cues: [{index, start, end, text}, ...]"""
    cues = []
    for m in _SRT_CUE_RE.finditer(srt_text):
        cues.append({
            "index": int(m.group(1)),
            "start": m.group(2),
            "end": m.group(3),
            "text": m.group(4).strip(),
        })
    return cues

def find_locator_for_evidence(evidence: str, cues: list[dict]) -> str:
    """Encontra o cue cujo texto contem o evidence text (substring match)."""
    evidence_lower = evidence.lower()[:100]  # primeiros 100 chars
    for cue in cues:
        if evidence_lower in cue["text"].lower():
            return f"{cue['start']}-{cue['end']}"
    return ""
```

### Para TXT/MD: numero de linha

```python
def find_line_locator(evidence: str, text: str) -> str:
    """Encontra a linha que contem o evidence text."""
    evidence_lower = evidence.lower()[:100]
    for i, line in enumerate(text.splitlines(), 1):
        if evidence_lower in line.lower():
            return f"line:{i}"
    return ""
```

---

## entry_id deterministico

```python
def make_entry_id(claim: str, source_file: str) -> str:
    """UUID deterministico baseado em content hash."""
    h = hashlib.sha256(f"{source_file}::{claim}".encode()).hexdigest()[:12]
    return f"ev-{h}"
```

---

## excerpt_hash

```python
def make_excerpt_hash(evidence_text: str) -> str:
    """Hash do trecho-fonte para integridade."""
    return hashlib.sha256(evidence_text.encode()).hexdigest()[:16]
```

---

## Integracao com compile.py

### Ponto de insercao: apos grounding check, antes de write_compilation

```python
# Evidence Ledger (§2.8) — provenancia por claim
if all_sections["principles"]:
    from evidence_ledger import build_ledger
    ledger = build_ledger(
        all_sections["principles"],
        filepath=str(filepath),
        source_hash=source_hash,
        source_metadata=source_metadata or {},
        source_content=content,  # texto puro (ja stripped)
        original_text=original_srt_text,  # SRT original com timestamps
    )
    all_sections["evidence_ledger"] = ledger
```

### read_source_metadata ja retorna upload_date ✅

### write_compilation: adicionar evidence_ledger ao JSON

```python
# Include evidence ledger if present (§2.8)
ledger = sections.get("evidence_ledger")
if ledger:
    data["evidence_ledger"] = ledger
```

---

## Integracao com semantic_field.py

### Substituir evidence_id posicional por entry_id real

```python
# ANTES (posicional):
"evidence_id": f"{source_file}#principle:{len(principle_nodes)}"

# DEPOIS (do ledger):
"entry_id": ledger_entry.get("entry_id", ""),
"evidence_id": ledger_entry.get("entry_id", ""),  # backward compat
"locator": ledger_entry.get("locator", ""),
"excerpt_hash": ledger_entry.get("excerpt_hash", ""),
```

### Para isso, build_semantic_field precisa receber o ledger

```python
def build_semantic_field(compilation: dict, evidence_ledger: dict = None) -> dict:
    """..."""
    # Mapear claims -> entries do ledger
    ledger_by_claim = {}
    if evidence_ledger:
        for entry in evidence_ledger.get("entries", []):
            ledger_by_claim[entry["claim"]] = entry
    
    # Ao criar principle node:
    entry = ledger_by_claim.get(statement, {})
    node["entry_id"] = entry.get("entry_id", "")
    node["locator"] = entry.get("locator", "")
    node["excerpt_hash"] = entry.get("excerpt_hash", "")
```

---

## Integracao com tiebreaker (Fase D)

Descomentar a ancora #3 no AUDITOR_FIXES_PLAN.md:

```python
# FUTURA (Fase D): ancora #3 — evidence_text do Evidence Ledger
for entry in evidence_ledger.get("entries", []):
    if entry.get("evidence_text") and new_salient & set(salient_terms(entry["evidence_text"])):
        return "creation"
```

---

## Arquivos

| Arquivo | Acao | Linhas (est.) |
|---------|------|-------------|
| `scripts/evidence_ledger.py` | **CRIAR** | ~200 |
| `tests/test_evidence_ledger.py` | **CRIAR** | ~200 |
| `scripts/compile.py` | **EDITAR** (integrar build_ledger) | ~20 |
| `scripts/semantic_field.py` | **EDITAR** (entry_id real, receber ledger) | ~25 |

---

## Verificacao

1. `pytest tests/test_evidence_ledger.py -v` — todos passam
2. `pytest tests/ -v` — 753+ testes continuam passando
3. `ruff check scripts/evidence_ledger.py` — limpo
4. Teste manual: compilar um SRT real, verificar que evidence_ledger.json tem locator com timestamps
5. Verificar que semantic_field.json usa entry_id real em vez de posicional
