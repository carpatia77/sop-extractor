# Architecture Reverse-Engineering Audit — "Blackhat Mode"

The opt-in fourth audit layer (Item 11). It reconstructs a **hypothesis** of a
demonstrated system's backend from its observable frontend — deducing what the
author did *not* reveal — while keeping that speculation walled off from the
anti-fabrication extraction core.

It is a **sibling of the coherence and evolution audits**, not a change to
extraction: it *consumes* an already-extracted skill and produces a separate
artifact, `<system>_architecture.md`. It never writes into `SKILL.md`.

> The hypothesis-generation pass is an isolated human+agent step (like the
> coherence audit), not pipeline code. This repo ships the **deterministic
> validator** (`scripts/validate_architecture_audit.py`) and the **candidacy /
> analyst-lens signals** in `scripts/preflight_scan.py`. Producing the artifact
> is your job; validating it honestly is the tool's.

## When it is offered (candidacy vs. intent)

- **Candidacy is detected from the material.** `preflight_scan.py` flags
  `re_candidate: true` when the source *demonstrates a system* — on-screen/UI
  deixis ("look at this", "olha aqui"), a repeated named system (e.g. `ASG`),
  outputs shown without their computation.
- **Intent is declared by you, never auto-selected.** Even on a 100%-candidate
  source the scanner only *offers* two options:
  - `[A]` faithful doctrine only (normal audit → `SKILL.md`) — **default**
  - `[B]` Blackhat Mode: faithful doctrine + this reverse-engineering layer
- **The analyst lens is proposed, then confirmed.** A generic base lens
  (`systems-architect`) plus the source's own salient vocabulary is surfaced so
  you sharpen it one-key (e.g. → `quantitative-systems-architect`). Nothing
  subject-specific is hardcoded, so the tool stays domain-agnostic.

## Artifact grammar (`<system>_architecture.md`)

**Front matter** (records the authorisation and the analytical POV):

```
---
intent: reverse-engineering
approved_by: <operator>
analyst_lens: <slug>
system: <name>
---
```

**Body** — bulleted claim lines, each carrying exactly one seal:

```
## Frontend observations
- [OBSERVED O1 part1/03:12] The dashboard paints a green marker at the value-area edge.
- [OBSERVED O2 part2/21:40] A "signal" fires only after price re-enters the value area.

## Inferred backend
- [INFERRED I1 ← O1, O2] The engine keeps a running TPO histogram and gates the
  signal on a value-area re-entry test.
```

- `[OBSERVED <Oid> <source_ref>]` — a fact the author showed/stated, traceable
  to a source location. `Oid` is `O1`, `O2`, …
- `[INFERRED <Iid> ← <Oid>[, <Oid>…]]` — a hypothesis about internal mechanism.
  `Iid` is `I1`, `I2`, …; the `←` list cites the OBSERVED evidence it rests on.

Only bulleted lines (`-`/`*`) are treated as claims; headings, prose, and table
rows are exempt from the Seal Gate.

## The four gates (`validate_architecture_audit.py`)

| Gate | Fails when |
|------|-----------|
| **Intent** | front matter lacks `intent: reverse-engineering`, a non-empty `approved_by`, or a non-empty `analyst_lens` |
| **Seal** | a claim line has zero or more than one seal |
| **Grounding** | an `[INFERRED]` cites no OBSERVED id, or cites an id not defined in the artifact. **Persona-blind** — an expert-sounding inference with no cited observation fails the same as a naive one |
| **Non-Contamination** | `SKILL.md` / `first_principles.md` / `sops.md` contain any `[INFERRED …]` seal (inference leaked into the faithful core) |

```bash
# Validate an artifact; --skill-dir enables the Non-Contamination Gate.
python scripts/validate_architecture_audit.py path/to/<system>_architecture.md \
    --skill-dir path/to/your-skill
```

Exit `0` only if all applicable gates pass. The Non-Contamination Gate is
skipped (not failed) if no skill dir or core files are found.
