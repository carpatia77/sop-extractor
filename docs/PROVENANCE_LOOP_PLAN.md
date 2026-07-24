# Plano de Implementação — Fechar o Loop de Proveniência

> **Objetivo:** a data que o Chronology Gate audita passa a vir da metadata capturada
> pela ingestão (`upload_date`), auto-preenchida no `set_manifest.json` como **proposta
> confirmável**, em vez de digitada à mão. Transforma a ingestão de "transcritor" em
> "semeador de proveniência datável", ligando a camada de ingestão à tese do projeto.

> **Escopo:** pequeno e cirúrgico. 1 script novo + 1 ajuste no prompt de extração + testes.
> **Não** mexe no evolution audit nem no schema do manifest (ambos já corretos).
> **Alvo de versão:** minor (feature aditiva).

---

## 1. O gap, em uma frase

`output/<id>/metadata.json` já tem `upload_date` (YYYY-MM-DD), `canonical_id`, `title` —
mas nada leva isso ao `set_manifest.json`, que hoje é 100% manual. O Chronology Gate
(`validate_evolution_audit.py`) valida contra a data do manifest; se ela é digitada errada,
o gate audita contra uma verdade falsa. Fechar o loop = auto-popular o manifest a partir
das metadatas de ingestão, com o humano confirmando.

---

## 2. Cadeia atual (referência — NÃO alterar estes)

| Arquivo | Papel | Muda? |
|---|---|---|
| `sopx/ingest/pipeline.py` | grava `metadata.json` c/ `upload_date`, `canonical_id`, `title`, `uploader`, `duration_seconds` | não (já correto) |
| `scripts/validate_manifest.py` | valida `set_manifest.json` (date `^\d{4}-\d{2}-\d{2}$`, `source_id` `^[a-z0-9][a-z0-9_-]*$`, `skill_path` dir existe, `sequence` int, tie-breaker de datas iguais) | não |
| `scripts/validate_evolution_audit.py` | lê `manifest[sid]={date,sequence}`, roda Chronology/Silence gates contra as tags | não |

---

## 3. O que construir

### 3.1 NOVO: `scripts/build_set_manifest.py` — o elo que faltava

Monta/atualiza `set_manifest.json` a partir de N diretórios de saída de ingestão.

**Interface CLI:**
```bash
# Monta o manifest de um Set a partir das ingestões + skills extraídas
sopx set-build <set_dir> --source output/<id1> --source output/<id2> ...
# ou varre um diretório de outputs
sopx set-build <set_dir> --from-outputs output/ --skills-root ./skills
sopx set-build <set_dir> --dry-run          # mostra o manifest proposto sem gravar
```

**Comportamento (funções puras, testáveis):**

```python
def source_id_from_metadata(meta: dict) -> str:
    """canonical_id -> source_id válido p/ o manifest (^[a-z0-9][a-z0-9_-]*$).
    Lowercase + troca inválidos por '-'. Ex.: 'mYDSSRS-B5U' -> 'mydssrs-b5u'.
    Para arquivo local sem canonical_id, usa slug do title/filename."""

def date_from_metadata(meta: dict) -> str | None:
    """Retorna upload_date (já YYYY-MM-DD) ou None. NUNCA fabrica.
    None => o membro entra com date vazia + flag 'needs_date' p/ o humano preencher
    (livro, arquivo local sem data, vídeo sem upload_date)."""

def infer_sequence(members: list[dict]) -> list[dict]:
    """Ordena por date; atribui 'sequence' 1..N. Datas iguais => mantém sequence
    explícito p/ satisfazer o tie-breaker do validate_manifest."""

def build_manifest(set_id: str, entries: list[dict], skills_root: str) -> dict:
    """Monta o dict do manifest. Cada entry = (output_dir, skill_path).
    Marca datas auto-preenchidas com um campo interno 'date_source': 'ingested'
    vs 'manual' (ver §3.3). Preserva overrides manuais existentes (merge, §3.4)."""
```

**Saída:** grava `set_manifest.json` e **roda `validate_manifest.py` no fim** (fail-fast:
se o manifest gerado não valida, aborta com o erro). Imprime um resumo:
```
  Set: fullcycle  (5 membros)
  ✓ src mydssrs-b5u   2019-03-12  seq 1   [ingested]
  ✓ src abc123def     2022-08-01  seq 2   [ingested]
  ⚠ src meu-livro     <SEM DATA>  seq ?   [needs_date] — preencha à mão
  → Próximo: sopx validate <set_dir>
```

### 3.2 Ajuste: data no prompt de extração — `scripts/preflight_scan.py`

`build_prompt_draft()` hoje carrega `lineage` mas **nenhuma data**. Se o `metadata.json`
do source estiver ao lado (ingestão), incluir a data capturada no prompt, para o agente
de extração escrever as tags de proveniência já ancoradas na data real (não num chute).

- Adicionar param opcional `source_date: str | None = None`.
- Se o scan recebe um `output/<id>/` (ou acha `metadata.json` irmão do source), lê
  `upload_date` e injeta uma linha no prompt: `SOURCE_DATE = 2019-03-12 [medido da ingestão]`.
- Se ausente: `SOURCE_DATE = <preencher> [não detectado]` — honesto, não inventa.

### 3.3 Regra de honestidade (o design que respeita a tese)

- Data de ingestão entra como **proposta rotulada** (`date_source: "ingested"`), nunca
  silenciosamente autoritativa.
- Sem data disponível → **campo vazio + flag `needs_date`**, jamais fabricada. O
  `validate_manifest.py` já rejeita date vazia/inválida, então um manifest incompleto
  falha o gate na hora (fail-fast) em vez de passar com data falsa.
- `upload_date` ≠ necessariamente data da doutrina (re-upload, republicação). O humano
  revisa e sobrescreve; ver §3.4.

### 3.4 Merge idempotente (re-rodar não apaga correções humanas)

Se `set_manifest.json` já existe: **preservar** qualquer `date` cujo `date_source` seja
`"manual"` (humano corrigiu). Só (re)preencher membros novos ou marcados `ingested`.
Chave de merge = `source_id`. Nunca clobar override humano.

---

## 4. Mapeamento de schema (ingest metadata → manifest member)

| manifest member | vem de `metadata.json` | regra |
|---|---|---|
| `source_id` | `canonical_id` | slugify → `^[a-z0-9][a-z0-9_-]*$` |
| `date` | `upload_date` | já YYYY-MM-DD; None → vazio + `needs_date` |
| `sequence` | — | inferido por ordem de data (§3.1) |
| `skill_path` | — | passado via `--skills-root` + convenção, ou `--source dir:skill` |
| `date_source` | — | `"ingested"` (auto) vs `"manual"` (humano) — campo auxiliar p/ merge |

> Nota: `date_source` é metadado de UI/merge. Se o `validate_manifest.py` for estrito
> quanto a campos extras, colocá-lo num bloco `_meta` por membro OU num sidecar
> `.set_manifest_meta.json`. **Verificar** se o validator permite campos extra antes de
> escolher — se rejeitar, usar o sidecar (não relaxar o validator).

---

## 5. Wiring no CLI

- `scripts/menu.py`: adicionar capability `set-build` (item 12), backing `build_set_manifest.py`.
  `is_available` só precisa checar o script (sem binário externo).
- Ajuda/`epilog` do `sopx ingest` já aponta o próximo passo `sopx scan`; adicionar menção:
  após ingerir vários vídeos de um autor, `sopx set-build <set_dir> --from-outputs output/`.

---

## 6. Testes (herméticos — sem rede/binário)

`tests/test_build_set_manifest.py`:
- `source_id_from_metadata`: `'mYDSSRS-B5U'` → `'mydssrs-b5u'`; título com espaços/acentos → slug válido.
- `date_from_metadata`: upload_date presente → passa; ausente → `None` (não fabrica).
- `infer_sequence`: ordem cronológica correta; datas iguais → sequences distintos.
- `build_manifest`: 3 metadatas fixture → manifest que **passa `validate_manifest()`**.
- **Regra needs_date:** membro sem upload_date → date vazia + flag, e o manifest gerado
  é rejeitado por `validate_manifest` até preencher (fail-fast comprovado).
- **Merge idempotente:** manifest pré-existente com date `manual` → re-run não sobrescreve.
- **Round-trip de integração:** manifest gerado + tags fixture → `validate_evolution_audit`
  passa o Chronology Gate (prova que a data auto-preenchida alimenta o gate de verdade).

`tests/test_preflight_scan.py` (+):
- `build_prompt_draft(..., source_date="2019-03-12")` inclui `SOURCE_DATE = 2019-03-12` no prompt.
- sem data → linha `<preencher>`, não inventada.

---

## 7. Critérios de aceite

- [ ] `sopx set-build` gera `set_manifest.json` válido a partir de N `output/<id>/`, com
      datas vindas de `upload_date`.
- [ ] Fonte sem data → membro `needs_date`, date vazia, **nunca fabricada**; manifest
      incompleto falha `validate_manifest` (fail-fast).
- [ ] Re-run preserva `date` marcada `manual` (override humano intacto).
- [ ] `source_id` sempre casa `^[a-z0-9][a-z0-9_-]*$`.
- [ ] Manifest gerado passa `validate_manifest` E alimenta o Chronology Gate em
      `validate_evolution_audit` (teste de round-trip verde).
- [ ] Prompt de extração carrega `SOURCE_DATE` medido quando a metadata existe.
- [ ] `set-build` no menu; ruff limpo (incl. `sopx/` e `scripts/`); zero regressão.
- [ ] `CHANGELOG` sob `[Unreleased]`.

---

## 8. Fora de escopo (não fazer agora)

- Não alterar `validate_evolution_audit.py` nem o schema do manifest (já corretos).
- Não construir "date drift detector" (tag diverge do upload_date) — stretch futuro.
- Não tentar datar livros automaticamente (sem sinal confiável; humano preenche).
- Não tocar na geração de Colab/importer.

---

## 9. Ordem sugerida (1-2 dias)

1. `build_set_manifest.py` funções puras + testes (§3.1, §6).
2. Merge idempotente + regra needs_date (§3.3, §3.4).
3. Round-trip com `validate_manifest`/`validate_evolution_audit` (teste-âncora).
4. Wiring no menu (§5).
5. `SOURCE_DATE` no `build_prompt_draft` + teste (§3.2).
6. CHANGELOG, ruff, regressão.

> **Processo (lição da Fase 0):** branch + PR + CI verde. Rodar o ruff no escopo COMPLETO
> do `ci.yml` (`book_to_skill/ sopx/ scripts/ tests/ tools/`) localmente antes de dizer
> "passou". Teste-âncora é o round-trip §6 — é ele que prova que o loop fechou de verdade.
