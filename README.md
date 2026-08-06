# Emotivus Forge 0.567

Forge provides portable, exact project truth and session continuity to AI models. It does not tell capable models how to reason, design, code, or debug.

> **Canonical repository:** `derickonfire/emotivus-forge` is the home of Forge development. New sessions should work out of this repo — see [`CLAUDE.md`](CLAUDE.md) for orientation.

## What 0.567 changes

- Opens the **Goal-3 cross-model evolution** work. Forward migration is now **guaranteed to preserve fields this Forge schema does not recognize**: an older or another vendor's package keeps its unknown top-level **and** nested fields verbatim through migration — locked by a regression, so a future refactor can't silently start dropping data.
- Forge now **reports what it carried through unrecognized** (`core/forward_compat.py`): the Resume Brief surfaces a `Forward-compat:` line listing preserved-but-unknown settings fields (only when any exist). Unknown fields are retained verbatim and **never interpreted, trusted, or treated as authority/evidence/lineage** — the honest cross-model primitive.
- This is the first piece of the G3 completion rule ("another model/vendor can migrate an older package, preserve exact meaning…"): Forge migrates without losing meaning, and tells you exactly what it didn't understand.
- Goal 1 remains certified **COMPLETE**; release authorization remains **false**.
- Certified suite grows additively to **536 focused public-neutral regressions across 56 deterministic isolated modules** (new `forward_compat` core module + `test_forward_compat`).
- Preserves the four-page website design and active generator.

## Current verification target

**536/536** focused public-neutral regressions across 56 deterministic isolated modules.

This count is package metadata until exact final-byte certification completes. It is not release authorization or proof of efficacy.

## Normal use

Say **Run Forge**. Forge identifies the project state and supplies verified context. The AI model remains responsible for reasoning and development.
