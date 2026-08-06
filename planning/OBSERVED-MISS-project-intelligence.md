# Observed miss — project intelligence on a real external project

**Type:** observed miss (expansion-rule ground truth) · **Recorded:** 0.555 cycle
**Trial:** Forge 0.555 run cold on the real Flask codebase (236 files), never
seen before. This is the first time Forge was exercised on a project other than
itself.

## What happened

`python3 forge.py` on a clean Flask clone produced a coherent Brief in ~170 ms
and did not crash. Balanced result:

### Genuine value (keep and expand)
- Identified the project as **Flask** from `pyproject.toml` (sourced, not guessed).
- Detected the technology stack (python, css, html, shell, sql).
- Observed all 236 files without truncation.
- **Automatically flagged `tests/test_apps/.env` as a sensitive-file REVIEW.**
  This is the single most useful thing Forge produced — an unprompted, real
  safety signal about the actual project.
- Held the refusal discipline: every unknown stayed `NOT_RUN`; no false claim.

### The miss (the product gap)
1. **Almost no project intelligence.** On a mature 236-file web framework, Forge
   learned **three** facts (name, stack, one secret candidate) and **zero
   architecture**. It cannot tell a cold model what Flask *is*, how `src/` is laid
   out, where the entry points are, how to run it, or where/how to test it — the
   exact things a cold agent or a non-expert owner needs first.
2. **~30 passport sections, ~90% empty ceremony.** `project_lineage`,
   `migration_identity`, `package_family`, `surface_coverage`, `release_facts`,
   `continuity_register`, `third_party_intakes`, `guardrails`, `field_trials`,
   `advanced_capabilities` all render as `NOT_DECLARED` / `NOT_RECORDED`. A reader
   wades through 30 "nothing here" sections to reach the 3 real facts.
3. **Blocks before giving value.** With no objective recorded, Forge's Brief and
   recommended prompt reduce to "stop and confirm your objective in a file" —
   process ceremony, not orientation. It demands input before offering insight.
4. **False-alarm feel.** A pristine, healthy clone immediately reports
   `self-currency: WARN`, purely because no objective is set.

## Declared ground truth (what the Brief SHOULD contain on first contact)

For the repurposed user (a cold agent, or a vibe coder who can't read the code),
the first Brief must answer, from the project itself, without an objective:

- **What is this?** One-line purpose inferred from README/pyproject/package
  metadata.
- **How is it built?** Entry points, top-level layout (`src/`, `tests/`, `docs/`),
  package/lock manager, declared scripts.
- **How do I run and test it?** The exact commands, read from `pyproject.toml` /
  `Makefile` / `package.json` / CI config — not invented.
- **What should I be careful of?** The secret/sensitive-boundary signals Forge
  already produces well, expanded (missing tests, risky patterns, large binaries).
- **What changed and why** (once there is history).

Everything else (lineage, migration, package-family, release-facts, …) is opt-in
depth, not first-contact content, and should be lazy — surfaced only when a
project actually declares it.

## Product implication (redirect Goal 1)

The sealed roadmap's Goal 1 (P2) consolidates the *schemas* behind the ~30
NOT_DECLARED sections. This trial shows that is hardening the ceremony, not the
value. **The higher-value Goal-1 work is a project-intelligence pass**: make the
Brief genuinely orient a cold model on an unfamiliar project, expand the
useful automatic signals, and make the 30 governance sections lazy/opt-in so they
stop drowning the 3 facts that matter.

Per the expansion rule this observed miss now authorizes a bounded implementation
and a scored trial: a richer first-contact orientation, measured again on Flask
(and one more external project) against this ground truth.

## Reproduce

```bash
git clone --depth 1 https://github.com/pallets/flask
cd flask && python3 /path/to/Emotivus-Forge/forge.py
cat .forge/resume.md .forge/passport.json
```
