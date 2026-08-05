# Forge — Final Recommendation

**Supersedes all prior documents in this set.** Absorbs
`FORGE-0548-ASSESSMENT-AND-REDIRECT.md`,
`FORGE-COMPLETION-MODEL-AND-EVIDENCE-LOOP.md` and
`FORGE-VERDICT-AND-SCOPE-CUT.md`. Those remain as evidence and detail; this is
the one to act from.

---

## ⚠️ READ THIS FIRST — THIS IS TESTIMONY, NOT EVIDENCE

Everything below came from one AI's trial of Forge 0.548 inside one sandboxed
session. Much of it was **executed** — cold runs, capability activation across
all nine, the graph run from the vault, a real defect caught at an exact line.
Some of it is **read**, and some is judgement.

**In the course of that same trial, three confident conclusions were wrong and
had to be withdrawn:**

1. "You built it and don't run it" — rested on a stale artifact from an early
   fork under an older name. Withdrawn entirely. It was the headline.
2. "Capability contracts are undocumented" — a complete working example shipped
   in the package all along. It was a routing failure, not a documentation gap.
3. "The benchmark has never been run" — it was attempted, and ruled inadmissible
   for reasons that turned out to matter more than the original claim.

**Do not let this document become a contract by virtue of being the newest one.**
Re-verify anything load-bearing — especially the status column in §5 — before
building against it.

That instinct, applied consistently, is the actual product. Everything below is
implementation detail.

---

# 🎯 THE VERDICT

**Keep about a fifth. Freeze the rest. Set an exit condition.**

Two of nine capabilities have working implementations. One caught a real defect
at an exact line. One produced better session handoff than a competent AI writes
by hand. **Everything else is bureaucracy wrapped around a small, good core.**

The core is worth finishing. The wrapper is worth freezing this month — not
deleted, but archived with a reason and removed from the roadmap.

---

# 🧬 THE ONE RULE THAT FUTURE-PROOFS EVERYTHING

**Split every feature — current and future — into *erodes* or *doesn't erode*.**

**Erodes** — a smarter model needs it less every month:
guidance text, recommended prompts, validation ceremony, documentation
explaining how an AI should behave.

**Doesn't erode** — no amount of intelligence substitutes for it:
a file's hash three weeks ago, a rendered pixel, an exact provider-reported
token count, a record that means the same thing to a different AI vendor.

**Why this is the decision rule and not just a category:** models are improving
fast. Anything built to compensate for a *confused* model becomes worthless as
models stop being confused. Anything that is simply *true regardless of
intelligence* becomes more valuable as sessions grow longer and the gap between
them gets more expensive to lose.

| Erodes → freeze | Doesn't erode → keep |
|---|---|
| `recommended_prompt` prose guidance | File fingerprint and quarantine detection |
| Capability activation contracts | Rendered-browser evidence |
| 75 documents, 22,500 words | Exact provider-reported token counts |
| `lab`, `evidence`, `confidentiality` (vaulted) | `resume.md` generated from ledger data |
| `ci-bridge`, `update` (deferred) | Portable continuity export, package-bound |
| `release-proof` (uncertified) | Structural checks that already work |
| The seven-goal percentage roadmap | A scored defect catch/miss table |

Left column is a wasting asset. Right column compounds.

---

# 🧠 THE STRICTER TEST — AND THE ONE MOST LIKELY TO BE MISSED

The erosion rule above is necessary but **not sufficient**, and this is the part
earlier drafts of this recommendation got wrong.

The question is not only *"will a smarter model still need this?"* It is:

> **"Does this survive the platform shipping it as a free feature?"**

Claude already has native memory and conversation search — automatic, no
ceremony, improving every release. Every major provider is heading the same way.
If context windows reach ten million tokens and cross-session memory becomes
standard with file-level provenance, **a large part of the generic handoff
problem is absorbed by the platform, for free, without Forge.**

What survives that:

1. **Cross-vendor portability.** A platform's memory does not transfer to a
   different AI company. A `resume.md` and a continuity export do, by design.
2. **Deterministic proof instead of probabilistic recollection.** Native memory
   is a model's best reconstruction. A ledger entry keyed to a file hash is
   either true or it is not.
3. **Rendered evidence.** A screenshot and an overflow measurement are true
   regardless of context size, model quality, or memory.

**Reframe goal 1 around exactly those and nothing else.** "Continuity" as a
general pitch is on borrowed time. **"Works when you switch models, and is
provably correct when it does"** is not.

---

# 🔪 THE KILL LIST — freeze this month

Apply the vault's own reconnection bar — a real trigger, a certified
implementation, a bounded budget, distinct value beyond native tooling — **to
the roadmap itself, not only to resurrection.** Nothing below clears it today.

- **`lab`, `evidence`, `confidentiality`** — vaulted, no implementation, no
  near-term trigger
- **`ci-bridge`, `update`** — deferred, no demonstrated need
- **`release-proof`** — uncertified; revisit only after `ship` is exercised and
  found wanting
- **The capability-contract ceremony** — schema versioning, budget ranges,
  `native_advantage.status`, five-item `focused_regressions` lists sourced from
  an internal catalog invisible without reading Python. **Delete outright.**
  Replace with a boolean and a one-line reason in a plain file
- **The seven-goal percentage roadmap** — replaced by the scoreboard in §6
- **Most of `docs/`** — hard cap: `RUN-FORGE.md` + `README.md` + `QUICKSTART.md`
  under 1,500 words combined; everything else moves to `reference/`, explicitly
  not required reading
- **Speculative checks** — never add a check for a defect class that has not
  actually occurred. **Reactive only, never speculative.** This is the
  discipline that stops goal 2 becoming the next 298 files

**Why freezing beats improving:** every item above gets *less* valuable as models
improve. Investing further in them is investing against the trend. This is
archival with a documented reason — the same thing the vault already does for
`lab` and `evidence` — applied consistently rather than selectively.

---

# ✅ THE KEEP LIST — finish this, and only this

| Item | Status | What remains |
|---|---|---|
| `NOT_RUN` instead of `PASS` on an unbaselined tree | Not built | One judgement call. **Largest single win** |
| Every blocker names its resolving artifact or command | Not built | Mechanical, across error paths |
| `forge` with no args resolving five states in code | Detection **proven**; routing not built | Replace `recommended_prompt` with the state machine |
| `forge close` replacing the eighteen-flag session close | Data **proven excellent** | Wrapper only |
| Structural checks — CSS structure, merge-marker, JSON | **PROVEN — caught a real defect at an exact line** | Nothing. Keep as-is |
| Graph — node inventory and subsystem discovery | **PROVEN — would have prevented a real mistake** | Recertify from vault, ship read-only |
| Graph — impact analysis | **Proven wrong** on dynamic PHP includes | Fix dynamic includes, or ship labelled "static reach only" |
| Browser evidence — overflow, DOM, screenshot | **Concept proven**; Forge's own tool never run | Accept rendered HTML, not only a static ZIP. **Highest-value open task** |
| Session Close → `resume.md` | **PROVEN — better than hand-written** | Nothing. Keep as-is |
| Portable continuity export, package-bound | **PROVEN** | Nothing. Keep as-is |
| Benchmark `OBSERVED` tier | Not built | New tier per §7; stop consuming tasks on failed attempts |
| First scored trial against six ground-truth defects | Not run | **The proof step. Do this before writing more code** |

Six proven items, four small fixes, one real piece of engineering. **A solo
developer can finish that. Nobody finishes 298 files across seven goals.**

---

# 📊 THE SCOREBOARD THAT REPLACES 89%

A percentage is a category error on an assurance tool. **You cannot be 90% done
at "does this catch defects."** It catches a class or it does not.

The evidence that the number was actively misleading:

| Signal | Value |
|---|---|
| Roadmap average | 89% |
| Capabilities with working implementations | 2 of 9 |
| Admissible benchmark results, ever | 0 |
| Defect classes with a recorded score | 0 |

**The number rose while the evidence stayed at zero.**

Replace it with two tables and nothing else:

| Defect class | Instrument | Caught | Missed | False positive |
|---|---|---|---|---|
| CSS structural break | `core.css-structure` | 1 | 0 | 0 |
| Unresolvable custom property | not built | 0 | 1 | — |
| Duplicate guard, cross-file | not built | 0 | 1 | — |
| Definition drift across screens | not built | 0 | 1 | — |
| Asymmetric delete behaviour | not built | 0 | 1 | — |
| Horizontal overflow | browser evidence | untested here | — | — |

**Current honest score: 1 of 6.** Worse-looking than 89%, and the first true
number the project has had — and unlike 89%, it says exactly what to build next.

---

# 🔁 THE LOOP — built, never turned once

What happened in this trial was a field trial: an external agent, cold, against
a real project with known ground truth, producing a scored assessment.

**The machinery to ingest that already exists and has never been used:**
`field-trial.example.json`, `field-observation.example.json`,
`INTEGRITY-FIELD-CAMPAIGNS.md`, `CHECK-QUALIFICATION.md`, and a `learn/`
directory holding exactly one example file.

**Turning it once is the highest-value action available.**

**The rule that makes it safe:**

```
field trial → MD (testimony, unverified)
                    ↓
        scored against declared ground truth
              ↓                    ↓
     findings with a          everything else
      known answer                  ↓
           ↓                     ADVICE
        LEDGER                (roadmap input,
       (evidence)            never a contract)
```

**Only the scored part enters the ledger.** Feed narrative MDs in raw — including
this one — and Forge learns opinions, some of them confidently wrong. See the
three retractions at the top of this document.

**And the benchmark needs an obtainable tier.** Its one attempt was ruled
inadmissible because the platform could not supply provider-reported token
counts — which no chat interface exposes to anyone. That condition makes the
benchmark unrunnable in the only environment Forge is used in, and permanently
burns an immutable task for trying. **Add an `OBSERVED` tier** using data that
can actually be obtained: turns to first productive action, corrections, retries,
output characters. Keep `EXACT` as the gold tier for API runs.

**A measurable proxy that gets run beats an exact metric that never does.**

---

# 🛑 THE STOP-LOSS — the most important section

**Ship the keep list. Run one real benchmark cycle. Then let the scoreboard
decide.**

- **If it shows real catches beyond the one already proven, and browser evidence
  runs on a server-rendered project → continue.** The tool is earning its place
  and the evidence says so.
- **If it does not → stop building new capability.** Keep only what already
  works: structural checks, Session Close, continuity export. Do not start
  another benchmark cycle, do not un-freeze anything from the kill list, do not
  add a tenth capability.

**Why this matters more than any feature:** this project has never had an exit
condition — only momentum. Seven goals at 89% is what momentum looks like when
nothing can fail. **A tool that cannot fail a test cannot prove it is worth your
time either.**

---

# 📋 FIRST FIVE ACTIONS, IN ORDER

1. **`NOT_RUN`, never `PASS`, on an unbaselined tree.** Hours. Removes the main
   reason trials look like failures.
2. **Delete the capability-contract ceremony.** Boolean plus a reason string.
   This removes most of the routing pain by removing the thing to route to.
3. **Fix browser evidence packaging** to accept rendered HTML. The one
   capability nothing else replaces — and it has never run on the class of
   project it exists to serve.
4. **Add the `OBSERVED` tier and run one real cycle** against the six defects.
5. **Apply the stop-loss.** Act on what the scoreboard says. Do not let the
   roadmap drift back to seven goals because stopping feels unfinished.

---

# 🎬 THE ONE-LINE ANSWER

> **Forge is worth finishing at about a fifth its current size. Keep what is true
> regardless of how smart models get — hashes, pixels, cross-vendor records.
> Freeze everything built to compensate for models being confused, because that
> problem is being solved by someone else. Then set a condition under which the
> answer is "stop," and honour it.**
