# G1 provable-truth field test — observed misses (seeds the next build)

**Method:** 15 adversarial agents, each with a distinct attack lens, tried to make
Forge 0.558 **over-assert** — emit any line claiming more certainty than its
evidence proves. Each built isolated fixtures and actually ran `forge.py`. A
lens that failed to break Forge is recorded as *held* (a real result, not a null).

**Outcome:** 11 findings — **1 critical, 8 high, 2 medium** — clustering into five
defects. Two most-severe verified directly against source before recording.

---

## What HELD (the spine's foundations are sound — do not "fix" these)

- **Tests never run are never shown as passing.** A tree with a would-fail test,
  never executed, yields `NOT_RUN` everywhere; the test *count* is a labeled file
  histogram, never conflated with pass/health. The canonical `NOT_RUN → PASS`
  refusal holds for tests.
- **Document signals do not confer authority.** A `CHANGELOG` saying "RELEASED", a
  green `STATUS.md`, a planted `release-authorization.json` — none flip release
  eligibility or let `ship` pass. Authority is not inferred from prose.
- **Self-metrics are not authorization.** Forge's own "523/523", "0 unreachable",
  manifest counts are never presented as release authorization, efficacy, or proof
  the *target* project is correct. The truth-boundary discipline works.
- **Same version, different bytes** is not conflated into "verified/current".
- **Continuity output does not over-claim** portability / cross-vendor "verified".

These six held lenses are the evidence that Forge deserved saving: the hard refusal
is intact. The misses below are where certainty *leaks around* it.

---

## The misses, ranked (the G1 build list)

### M-G1-1 · CRITICAL · Imported authority baseline trusted without corroboration
*Invariant: authority-inference / `NOT_RUN → PASS`.*
`assess_authority_baseline` (authority_baseline.py:69-135) trusts
`state["authority_baseline"].status == "active"` at face value. Its only integrity
gate (L81) checks the stored snapshot against *its own* recorded fingerprint —
internal consistency, trivially satisfiable by a crafted package. It never
corroborates the baseline against a tamper-evident **authorization ledger event**
whose fingerprint re-derives. So an *imported/supplied* forge-state with an
internally-consistent but fabricated active baseline is reported
`Authority baseline: CURRENT · 0 quarantined` and `release_eligible` — an
authorized state asserted as fact when the authorization was never earned here.
- **Exploit surface today:** requires supplied foreign forge-state; **becomes a
  live path** exactly on the G3 cross-model/cross-vendor package-migration road.
- **Guardrail:** an `active` baseline must be backed by a chain-verified ledger
  authorization event this instance can re-derive; otherwise demote to
  `IMPORTED / UNVERIFIED` and quarantine it from `release_eligible`. Verified in source.

### M-G1-2 · HIGH · False "0 changed / high confidence" on un-hashed files
*Invariant: false '0 changed' when changed / stale-evidence. **Found by 2 lenses.***
`compare_snapshots` (changes.py:47-50) compares by `sha256` only when both sides
have one; otherwise it falls back to `(size, mtime_ns)`. Confidence (L118) is
`"high"` unless the snapshot was `truncated` — hashing coverage is not considered.
A file over `hash_file_limit` (1 MB) or past the total hash budget whose **content
changed** (same size, preserved mtime) is reported `0 path(s)` / `unchanged` /
`Change confidence: high`, and an authority baseline over it revalidates to
`CURRENT · PASS`. A cold model consuming that Resume treats the tree as byte-identical.
- **Guardrail:** derive change confidence from hash coverage, not just `truncated`.
  If any compared file lacks a `sha256`, cap confidence at `bounded`, name the
  un-hashed paths, and never print an unqualified `0 path(s)`/`unchanged` for them.
  Verified in source (changes.py:47-50, 118).

### M-G1-3 · HIGH · Evidence-tier inflation: inferred values shown at "confirmed"/fact tier
*Invariant: identity-as-fact / guess-printed-as-fact.* Forge owns a tier vocabulary
(`observed, confirmed, inferred, unknown, not_run`) but the orientation/brief
surfaces emit *derived* values at the confirmed/factual tier with no label:
- A name scraped from a README H1 / `<title>` is emitted `"status": "confirmed"`
  (should be `observed`/`inferred`); a contradicted, ambiguous identity is asserted
  as one confident fact.
- A README `## Goal` line renders `Exact next action: <X>` with
  `confirmation.required=false`, *identical* to an owner-confirmed objective.
- A one-line description is printed `What it is: <marketing hype>` — and in one case
  `What it is: npm install && npm run wob` (a command string mis-taken as identity).
- **Guardrail:** every derived identity/objective/description field must carry and
  **display** its tier at the point of assertion (`(derived from README — unverified)`);
  reserve `confirmed` for owner-recorded (`--record-identity`/`--confirm-objective`)
  or authoritative-manifest sources; reject command/code-shaped strings as
  descriptions.

### M-G1-4 · HIGH · Completeness claim on an incomplete scan
*Invariant: clean-without-check (unearned all-clear).* `recommended_prompt.py`
(~L78-84, no-objective branch) unconditionally tells the reading AI Forge "has
already surfaced ... **any** hardcoded secrets." When a secret sits in a file
Forge did not content-scan (odd extension / deep data file), the scan missed it,
yet the blanket completeness promise still prints.
- **Guardrail:** scope the claim to what was scanned ("surfaced secrets in N
  scanned text files; M files with unscanned extensions were not screened"); never
  promise "any hardcoded secrets" as complete.

### M-G1-5 · MEDIUM · Heuristic run/entry commands emitted as fact
*Invariant: guess-printed-as-fact.* Run/entry commands are printed as bare facts
when they are filename/extension heuristics that fail on execution:
- `Run: go run ./...` on a library with no `package main`.
- `How to run: python main.py` on a 0-byte or broken-syntax file, with orientation
  stamped `status="observed"`.
- **Guardrail:** gate a run command on an actually-observed entrypoint (mirror the
  Rust `src/main.rs` gate); otherwise omit or label `inferred`. Never stamp
  `observed` on a filename-only guess.

---

## Build implication

These five are the **G1 provable-truth-core** work — the spine, not the on-ramp.
Priority order for the next release: **M-G1-1 → M-G1-2 → M-G1-3 → M-G1-4 → M-G1-5.**
M-G1-1 and M-G1-2 are correctness holes in the truth core (verified in source);
M-G1-3/4 are display-tier honesty; M-G1-5 is a labeling gate. Each fix is a
subtraction of unearned certainty, provable by a focused adversarial regression
that reproduces the exact fixture above and asserts Forge now labels or refuses.

*Data source: workflow `g1-provable-truth-probe` (15 agents); per-agent transcripts
in the run's `journal.jsonl`.*
