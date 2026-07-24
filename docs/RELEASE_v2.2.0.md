# Release v2.2.0 — Fechamento do Loop de Proveniência

**Data:** 2026-07-24
**Tipo:** Feature release (minor)

---

## Resumo

Esta versão fecha o **loop de proveniência** entre ingestão e auditoria temporal — a funcionalidade core que diferencia o sop-extractor de qualquer outra ferramenta de conhecimento no mercado.

---

## O que mudou

### Novo: `sopx set-build` — Build de Manifest Automático

O comando `set-build` auto-preenche `set_manifest.json` a partir das metadadas de ingestão, fechando o gap entre "o que foi ingerido" e "o que o Chronology Gate audita".

```bash
# Montar manifest a partir de outputs ingeridos
sopx set-build ./meu-set --source output/vid1 --source output/vid2

# Auto-detectar todos os outputs
sopx set-build ./meu-set --from-outputs output/

# Visualizar sem gravar
sopx set-build ./meu-set --dry-run
```

**Funcionalidades:**
- Extração automática de `upload_date` e `canonical_id` do `metadata.json`
- Conversão de `canonical_id` para `source_id` válido (slugify)
- Inferência de sequência cronológica
- Merge idempotente (preserva correções humanas)
- Validação com `validate_manifest.py` real (fail-fast)

### Novo: `SOURCE_DATE` no Prompt de Extração

O prompt de extração agora inclui a data medida da ingestão:

```
Configuração (auto-detectado + defaults — revise):
  BOOK_TYPE = transcript  ([medido] Transcript (.srt/.vtt))
  DEPTH     = study  [default: study]
  Nome      = mydssrs-b5u
  SOURCE_DATE = 2026-07-22  [medido da ingestão]  ← NOVO
```

**Regra de honestidade:**
- Data existe → `SOURCE_DATE = YYYY-MM-DD [medido da ingestão]`
- Data não existe → `SOURCE_DATE = <preencher> [não detectado]`
- **Nunca fabrica dados**

---

## Regra de Honestidade (Design Core)

O loop de proveniência segue a filosofia **"propose, don't guess"**:

1. **Data medida entra como proposta** (`date_source: "ingested"`), nunca silenciosamente autoritativa
2. **Sem data → campo vazio + flag `needs_date`**, jamais fabricada
3. **Re-run preserva correções humanas** (`date_source: "manual"`)
4. **Fail-fast**: manifest com data vazia falha `validate_manifest` imediatamente

---

## Arquivos Alterados

| Arquivo | Mudança |
|---------|---------|
| `scripts/build_set_manifest.py` | **NOVO** — Script principal com funções puras testáveis |
| `scripts/preflight_scan.py` | Adicionado `source_date` ao prompt draft |
| `scripts/menu.py` | Capability #12 `set-build` |
| `tests/test_build_set_manifest.py` | **NOVO** — 27 testes |
| `tests/test_preflight_scan.py` | +2 testes para SOURCE_DATE |

---

## Testes

- **543 testes passando** (29 novos nesta versão)
- **Ruff limpo** (incluindo `sopx/`)
- **Round-trip test**: manifest gerado → `validate_manifest` → Chronology Gate

---

## Impacto no Mercado

| Capacidade | sop-extractor | Concorrentes |
|------------|:-------------:|:------------:|
| Loop de proveniência | ✅ Automático | ❌ Manual/inexistente |
| Anti-fabricação de datas | ✅ Regra rígida | ⚠️ Confia no LLM |
| Merge idempotente | ✅ Preserva humanos | ❌ Não faz |
| Fail-fast em dados incompletos | ✅ Validação real | ❌ Não valida |

**Nenhum outro tool de conhecimento fecha esse loop automaticamente.**

---

## Breaking Changes

Nenhum. Esta é uma feature aditiva.

---

## Deprecations

Nenhuma.

---

## Upgrade

```bash
pip install -e ".[ingest]"
```

---

## Exemplo de Uso Completo

```bash
# 1. Ingerir vídeos
sopx ingest https://youtube.com/watch?v=vid1
sopx ingest https://youtube.com/watch?v=vid2

# 2. Montar manifest (NOVO)
sopx set-build ./meu-set --from-outputs output/

# Output:
#   Set: meu-set  (2 membros)
#   ✓ src vid001   2024-01-15  seq 1   [ingested]
#   ✓ src vid002   2024-03-20  seq 2   [ingested]
#   → Próximo: sopx validate ./meu-set

# 3. Validar
sopx validate ./meu-set

# 4. Extrair skills
sopx scan output/vid001/transcript.srt --emit-prompt
# Prompt agora inclui: SOURCE_DATE = 2024-01-15 [medido da ingestão]
```

---

## Agradecimentos

Obrigado ao engenheiro auditor que identificou os 2 problemas críticos na revisão:
1. Reimplementação do validator que divergia do real
2. SOURCE_DATE nunca sendo preenchido de verdade

Ambos corrigidos antes do merge.

---

## Próximos Passos

- v2.3.0: Batch channel ingestion (processar playlists inteiras)
- v2.4.0: Frame extraction com VLM (análise visual)
- v3.0.0: Teach Mode (Fase 1)
