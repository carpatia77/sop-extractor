# Knowledge-Compilation Pipeline — Architecture

End-to-end structure that turns a bibliography (books + video courses) into a
consistent, time-traceable doctrine. This diagram is a **corrected** version of
an earlier draft — see "Accuracy notes" at the bottom for what was fixed and
why, so the corrections aren't silently re-introduced later.

```mermaid
flowchart TD
    classDef raw fill:#2d3748,stroke:#4a5568,color:#e2e8f0;
    classDef ai fill:#3182ce,stroke:#2b6cb0,color:#fff;
    classDef output fill:#38a169,stroke:#2f855a,color:#fff;
    classDef script fill:#d69e2e,stroke:#b7791f,color:#fff;
    classDef gate fill:#e53e3e,stroke:#c53030,color:#fff;
    classDef human fill:#805ad5,stroke:#6b46c1,color:#fff;

    subgraph Phase1 [Phase 1: Per-Source Extraction]
        A1[("Raw sources<br>books &amp; video courses")]:::raw -->|LLM base pass| A2("Individual extraction<br>per work"):::ai
        A2 --> A3["SKILL.md · chapters/*.md<br>first_principles.md<br>sops.md · glossary.md"]:::output
        A1 -. "transcript srt" .-> V1{{"extract_frames_at_timestamps.py"}}:::script
        V1 --> V2["frames/*.jpg<br>frames_manifest.json"]:::output
        V2 -. "cited in" .-> A3
    end

    subgraph Phase2 [Phase 2: Per-Source Validation]
        A3 --> M1{{"determinism_score.py"}}:::script
        M1 --> M2["determinism_score.json<br>(structural measure, not pass/fail)"]:::output
        A3 --> M3{{"verify_concept_presence.py"}}:::script
        M3 --> M4["Traceability triage<br>principles vs. transcript"]:::output

        A3 -->|isolated LLM session| CA(Coherence Audit):::ai
        CA --> CB["coherence_audit.md<br>(flagged tensions)"]:::output
        CB --> CV{{"validate_coherence_audit.py"}}:::script
        CV -->|">30% citations unverified<br>= hallucinated"| CA
        CV -->|"citations real, real tensions found"| PD["PENDING_DOCTRINAL_<br>DECISIONS.md"]:::output
        PD --> HR(Human judgment):::human
        HR -. "optional edits" .-> A3
    end

    subgraph Phase3 [Phase 3: Chronological Grouping]
        A3 --> C1["set_manifest.json<br>chronological order (+ sequence tie-breaker)"]:::raw
        C1 --> C2{{".evolution_audit_prompt.md"}}:::script
    end

    subgraph Phase4 [Phase 4: Isolated Cross-Source Audit]
        C2 -->|zero-context handoff| D1(Isolated LLM session):::ai
        A3 -->|"reads all sources fp/sops/glossary"| D1
        D1 --> D2["<set>_evolution.md<br>lineage matrix"]:::output
        D1 --> D3["<set>_current.md<br>reconciled doctrine + provenance"]:::output
    end

    subgraph Phase5 [Phase 5: The Validation Gates - sequential, short-circuit]
        D2 --> E1{{"validate_evolution_audit.py"}}:::script
        D3 --> E1
        E1 --> F1[Chronology Gate<br>no time-travel]:::gate
        F1 --> F2[Silence Gate<br>no mute revocations]:::gate
        F2 --> F3["Confidence Gate<br>dropped? must be low-confidence"]:::gate
        F3 --> F4[Claim Verification<br>traces tags to source]:::gate
    end

    F1 -->|fail| D1
    F2 -->|fail| D1
    F3 -->|fail| D1
    F4 -->|fail| D1
    F4 -->|"all claims verified"| G1((("Final Framework<br>validated & hardened"))):::output

    PYT["pytest tests/ — 203 tests<br>validates the SCRIPTS, not the content"]:::script
```

## How the pipeline prevents hallucination

1. **Zero-context handoff (isolation)** — both the Coherence Audit (Phase 2)
   and the cross-source Evolution Audit (Phase 4) run in a *fresh* LLM
   session that does not inherit the prep deliberations. This forces a cold
   read and prevents the agreement bias where a model rubber-stamps something
   because it said it earlier.
2. **Rigorous provenance tags** — every rule in the final `<set>_current.md`
   must end in a tag like `[src2/2025-01-01, base: src1/2019-01-01]`.
   If a tag cites a source that doesn't exist or a claim the source text
   doesn't support, `validate_evolution_audit.py` fails the build in Phase 5.
3. **Chronology Gate** — logically forbids an older source from superseding a
   newer one within a concept's lineage (with an explicit `sequence`
   tie-breaker for same-dated sources).
4. **Two distinct failure meanings, never conflated** — a *validator* failure
   (Phase 2 coherence or Phase 5 evolution) means **hallucinated citations →
   regenerate the audit**. A *flagged tension* on the success path means
   **a real doctrinal question → human judgment** (`PENDING_DOCTRINAL_DECISIONS.md`).
   These are different roads; mixing them would let a real contradiction hide
   behind "the script passed."

## Accuracy notes (corrections from the earlier draft)

- **Coherence validator direction fixed.** `validate_coherence_audit.py` only
  checks *citation traceability* (are the flagged Claim A/B quotes real, ≥70%
  verified). Its **failure** means hallucinated citations → regenerate, **not**
  a doctrinal decision. `PENDING_DOCTRINAL_DECISIONS.md` is fed by the audit
  **passing** and surfacing genuine tensions for human review — the earlier
  draft had this arrow backwards.
- **Pytest is not in the content flow.** The 203 tests validate the Python
  scripts themselves; they are not a stage of content validation and were
  wrongly fused with the coherence-validator success path before. Shown
  off to the side here. (Count was also stale at "191".)
- **Video sub-pipeline added.** `extract_frames_at_timestamps.py` → `frames/`
  + `frames_manifest.json` → `## Visual Reference` citations was absent from
  the earlier draft, which read as text-only.
- **Measurement layers added.** `determinism_score.py` (structural
  determinism %, not a pass/fail gate) and `verify_concept_presence.py`
  (principle-vs-transcript traceability triage) were both missing.
- **Confidence Gate label precised.** It specifically rejects a `dropped?`
  transition marked with high confidence — not a vague "requires uncertainty
  flags."
- **Isolation shown for both audits.** The Coherence Audit is isolated too
  (SKILL.md Step 9.6 hands off to a new session), not just the Evolution Audit.
- **Environment de-specified.** The isolated session isn't tied to a specific
  OS ("Ubuntu" was incidental); what matters is that it's context-isolated.
- **Gates are sequential, not parallel.** They short-circuit — the first gate
  to fail returns non-zero; a failure routes back to regeneration, it doesn't
  "fix the gate."
