<h1 align="center">sop-extractor</h1>

<p align="center">
  <strong>Transforme livros e cursos em vídeo em uma base de conhecimento auditável que um LLM pode usar.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=for-the-badge" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/tests-203%20passing-38a169?style=for-the-badge" alt="Tests">
  <a href="README.md"><img src="https://img.shields.io/badge/EN-English%20Version-blue?style=for-the-badge" alt="English Version"></a>
</p>

---

## O que é

A maioria das ferramentas "converse com seus documentos" faz **busca** (RAG). Este projeto faz **compilação**: extrai a lógica de decisão de um autor como **Princípios Fundamentais** (verdades irredutíveis) e **SOPs** (procedimentos executáveis), e marca as partes incertas como **Heurística** em vez de fingir determinismo.

Funciona com **uma única fonte** — um livro, um curso, uma pasta de documentos — e já entrega uma skill com rastreabilidade completa. Quando você tem várias obras do mesmo autor, **audita como a doutrina evoluiu ao longo do tempo**.

---

## Comece em 3 comandos

### 1. Instale

```bash
git clone https://github.com/carpatia77/sop-extractor.git
cd sop-extractor
pip install -e .
```

### 2. Escaneie um PDF

```bash
sopx scan caminho/para/seu-livro.pdf --emit-prompt
```

O scan analisa o PDF e imprime um prompt pronto para copiar e colar no seu agente (Claude, Copilot, Amp, etc).

### 3. Valide o resultado

```bash
sopx validate caminho/para/sua-skill
sopx view caminho/para/sua-skill    # abre uma página HTML legível
```

---

## Como funciona (resumo)

```
Seu PDF/curso
    │
    ▼
  ┌─────────────┐
  │  PRE-FLIGHT  │  scan detecta tipo de conteúdo
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  EXTRACT     │  agente LLM extrai princípios e SOPs
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  AUDIT       │  validadores determinísticos verificam
  └──────┬──────┘     coerência, cronologia, citações
         ▼
  ┌─────────────┐
  │  SKILL       │  resultado: skill pronta para usar
  └─────────────┘
```

---

## Formatos suportados

PDF, EPUB, DOCX, TXT, Markdown, reStructuredText, AsciiDoc, HTML, RTF, MOBI/AZW — e transcrições de vídeo **SRT/VTT**.

---

## O que a skill gerada contém

| Arquivo | O que é |
|---------|---------|
| `SKILL.md` | Princípios Fundamentais + SOPs + índice |
| `chapters/ch01-*.md` | Um arquivo por capítulo (livro) ou módulo (curso) |
| `first_principles.md` | Princípios essenciais, cada um com sua causa e fonte |
| `sops.md` | Procedimentos executáveis e tabelas de decisão |
| `glossary.md` | Termos-chave, ordenados |

---

## Modo avançado

```bash
# Curso multi-parte (2+ arquivos)
sopx scan parte1.srt parte2.srt --emit-prompt

# Ver todas as opções do menu interativo
sopx

# Só uma auditoria específica
sopx coherence arquivo_auditoria --dir caminho/para/sua-skill
sopx determinism caminho/para/sua-skill
```

---

## Por que não só...

**...jogar o livro inteiro no contexto?** Você paga o custo de tokens **em cada turn de cada sessão, para sempre**. Compilação paga o custo uma vez; cada pergunta posterior carrega apenas o necessário.

**...usar RAG?** RAG indexa uma estante; este projeto domina uma obra. São complementares — para duzentos livros use RAG; para um autor com quem você quer raciocinar, compile.

---

## Licenca

**Apache 2.0** — aplicável ao código deste repositório (excluindo `book_to_skill/` que continua sob MIT).

Veja [NOTICES.md](NOTICES.md) para detalhes de licenças de terceiros.

---

## Créditos

- **[book-to-skill](https://github.com/virgiliojr94/book-to-skill)** por **virgiliojr94** (MIT) — motor de extração e formato de skill.
- A camada de auditoria (scoring de determinismo, auditoria de coerência, auditoria temporal com 4 gates, resgate de frames de vídeo) é a adição deste projeto.
