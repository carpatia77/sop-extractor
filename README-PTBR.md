<h1 align="center">sop-extractor</h1>

<p align="center">
  <strong>Transforme livros e cursos em video em uma base de conhecimento auditavel que um LLM pode usar.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=for-the-badge" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/tests-203%20passing-38a169?style=for-the-badge" alt="Tests">
  <a href="README.md"><img src="https://img.shields.io/badge/EN-English%20Version-blue?style=for-the-badge" alt="English Version"></a>
</p>

---

## O que e

A maioria das ferramentas "converse com seus documentos" faz **busca** (RAG). Este projeto faz **compilacao**: extrai a logica de decisao de um autor como **Primeiros Principios** (verdades irredutiveis) e **SOPs** (procedimentos executaveis), e marca as partes incertas como **Heuristica** em vez de fingir determinismo.

Funciona com **uma unica fonte** — um livro, um curso, uma pasta de documentos — e ja entrega uma skill com rastreabilidade completa. Quando voce tem varias obras do mesmo autor, **audita como a doutrina evoluiu ao longo do tempo**.

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
sopx view caminho/para/sua-skill    # abre uma pagina HTML legivel
```

---

## Como funciona (resumo)

```
Seu PDF/curso
    │
    ▼
  ┌─────────────┐
  │  PRE-FLIGHT  │  scan detecta tipo de conteudo
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  EXTRACT     │  agente LLM extrai principios e SOPs
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  AUDIT       │  validadores deterministicos verificam
  └──────┬──────┘     coerencia, cronologia, citacoes
         ▼
  ┌─────────────┐
  │  SKILL       │  resultado: skill pronta para usar
  └─────────────┘
```

---

## Formatos suportados

PDF, EPUB, DOCX, TXT, Markdown, reStructuredText, AsciiDoc, HTML, RTF, MOBI/AZW — e transcricoes de video **SRT/VTT**.

---

## O que a skill gerada contem

| Arquivo | O que e |
|---------|---------|
| `SKILL.md` | Primeiros Principios + SOPs + indice |
| `chapters/ch01-*.md` | Um arquivo por capitulo (livro) ou modulo (curso) |
| `first_principles.md` | Principios essenciais, cada um com sua causa e fonte |
| `sops.md` | Procedimentos executaveis e tabelas de decisao |
| `glossary.md` | Termos-chave, ordenados |

---

## Modo avancado

```bash
# Curso multi-parte (2+ arquivos)
sopx scan parte1.srt parte2.srt --emit-prompt

# Ver todas as opcoes do menu interativo
sopx

# Só uma auditoria especifica
sopx coherence arquivo_auditoria --dir caminho/para/sua-skill
sopx determinism caminho/para/sua-skill
```

---

## Por que nao so...

**...jogar o livro inteiro no contexto?** Voce paga o custo de tokens **em cada turn de cada sessao, para sempre**. Compilacao paga o custo uma vez; cada pergunta posterior carrega apenas o necessario.

**...usar RAG?** RAG indexa uma estante; este projeto domina uma obra. Sao complementares — para duzientos livros use RAG; para um autor com quem voce quer raciocinar, compile.

---

## Licenca

**Apache 2.0** — aplicavel ao codigo deste repositorio (excluindo `book_to_skill/` que continua sob MIT).

Veja [NOTICES.md](NOTICES.md) para detalhes de licencas de terceiros.

---

## Creditos

- **[book-to-skill](https://github.com/virgiliojr94/book-to-skill)** por **virgiliojr94** (MIT) — motor de extracao e formato de skill.
- A camada de auditoria (scoring de determinismo, auditoria de coerencia, auditoria temporal com 4 gates, resgate de frames de video) e a adicao deste projeto.
