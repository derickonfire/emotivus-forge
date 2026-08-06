# Decision Forks and Cross-Model Consistency

Forge detects bounded, high-impact design conflicts before implementation when the observed requirement cannot be represented honestly by the current project model.

## Current detector

The first neutral detector identifies a deadline-precision fork:

- the project currently stores or accepts calendar dates without time-of-day precision;
- an authoritative requirement or interface introduces Immediate, 15 Minutes, 30 Minutes, or another exact-time deadline.

Forge then presents:

- the existing constraint;
- the requested capability;
- concrete options and implications;
- a recommendation;
- the authority required to decide.

Forge does not silently select an architecture.

## Resolve through Adopt

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --resolve-fork deadline-precision=add-optional-exact-time \
  --fork-rationale "Represent exact deadlines honestly while preserving historical date-only records." \
  --fork-authority owner
```

The append-only Ledger stores the accepted option, all rejected options, rationale, authority, constraint, and triggering evidence. The existing eight-file state model is preserved.

## Cross-model context

Resume includes a stable **Governing decisions** section. It is model-neutral and does not change based on whether Claude, ChatGPT, or another coding agent reads it.

## Contradiction warning

After a decision is confirmed, Resume compares observed changed work with that decision. It warns when implementation appears to reintroduce a rejected option, such as mapping minute-level deadlines into date-only values after optional exact-time storage was approved.

A warning is governance evidence, not proof that the implementation is defective. The relevant code and project-native checks still require review.
