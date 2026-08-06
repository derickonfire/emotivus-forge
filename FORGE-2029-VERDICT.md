# Forge — The 2029 Verdict

*Should this project live, and if so, as what?*

**Decision: SAVE — and sharpen.** Forge is not a coding tool that AI is about to
make obsolete. It is a *trust-and-continuity substrate for AI-built software*, and
the faster models advance, the more that substrate is needed. What must die is the
ceremony. What must live is the discipline.

This document is the honest reasoning behind that call. It is deliberately not a
sales pitch. If the bear case had won, this file would say "retire it," and it
would say why.

---

## 1. What Forge actually is

Strip away 88 modules, 76 docs, and nine versions of accumulated vocabulary, and
Forge does one thing:

> **It gives a cold AI model a trustworthy, deterministic answer to "what is true
> about this project right now, who authorized it, what changed, what's the
> evidence, and what is the exact next action" — and it refuses to lie about any
> of those things.**

It sits *beside* the model, not inside it. The model reasons, designs, codes, and
debugs. Forge owns the boring, non-negotiable facts: exact identity (SHA-256 of
files, trees, packages), authority (who signed off on this baseline), lineage
(what this was forked or migrated from), evidence (did the check actually run, or
are we pretending), and continuity (what the last session left for the next one).

Its single most important behavior is a *refusal*: Forge will not convert a hope
into a fact. A check that never ran is `NOT_RUN`, never `PASS`. Reachability is
not deletion authority. An AI's claim of "done" stays unverified until code and
evidence back it. This refusal is the whole product. Everything else is plumbing.

The public surface is five commands (Help, Adopt, Resume, Check, Ship) collapsed
behind one human instruction: **"Run Forge."**

## 2. The state we inherited (0.552)

Verified, not asserted:

- **Runtime works.** `python3 forge.py` produces a coherent Forge Brief on a cold
  project. Confirmed live in this session.
- **All 523 tests pass** across 54 isolated modules, in ~45s, with no freeze. The
  0.552 self-test runner fixed the interpreter-shutdown stall that made earlier
  builds hang.
- **88 runtime modules, 0 statically unreachable, 0 unclassified.** Every active
  path has a declared purpose.
- **The project self-verifies.** Its own docs, manifest, checksums, roadmap, and
  website are cross-checked by tests. You cannot quietly desync the story from the
  code — a rare and valuable property.

So we are not reviving a corpse. We are deciding the future of a healthy but
*over-grown* system.

## 3. The real question: is this useful in 2029?

Assume the bull case for AI: models in 2029 have enormous context, strong memory,
and run as autonomous multi-step agents that write most production code. Does a
deterministic project-truth layer still matter, or does the model just… know?

### The bear case (why Forge could die)

- Context windows swallow whole repos; the model re-derives state on every run.
- Git already carries identity, lineage, and diffs. CI already carries evidence.
- Agent harnesses (Claude Code, Cursor, and successors) already orient themselves.
- Forge's ceremony — dozens of `adopt` flags, attestation kits, an eight-state
  representation — is heavy, and heavy things get routed around.

This case is real. If Forge stays what it is today, it loses.

### The bull case (why Forge gets *more* important)

The bottleneck in software is moving. It is no longer "can the AI write the code."
It is **"can anyone trust what the AI and the fleet of agents just did, and hand it
cleanly to the next one."** Capability is becoming abundant; *verified trust* is
becoming scarce. Forge lives exactly on the scarce side.

Four forces make it more relevant, not less:

1. **Vibe coders ship code they cannot read.** As non-experts push AI-generated
   systems to production, the only thing standing between them and a confident-but-
   false "it's ready" is a layer that mechanically refuses to upgrade `NOT_RUN` to
   `PASS`. That is Forge's core reflex. Bigger models make *more* confident claims,
   not fewer — so the refusal matters more.

2. **Multi-agent, multi-vendor hand-offs need a neutral ledger.** When a Claude
   agent, a GPT agent, and a local model all touch the same repo across a week,
   "what is true and who authorized it" cannot live inside any one model's memory.
   It needs a vendor-neutral, deterministic record any of them can pick up. Git
   doesn't carry objective, authority baseline, decision forks, evidence tier, or
   the exact next action. Forge does. This is G3, and it is the durable moat.

3. **Provenance becomes compliance.** Attestation, supply-chain integrity, and
   "prove this artifact is what you say it is" move from nice-to-have to regulated
   requirement as AI-authored code enters critical systems. Forge already speaks
   exact-byte identity, owner-keyed attestation, and evidence binding fluently.

4. **Bigger context does not equal grounded truth.** A model that *can* read the
   whole repo still hallucinates about it. A deterministic external oracle that
   says "the tree hash is X, the check is NOT_RUN, the baseline was authorized by
   owner on date Y" is precisely the grounding that scaling context does not
   provide. Forge is anti-hallucination infrastructure.

**Verdict:** the durable core wins the argument. Forge survives — *if* it sheds the
ceremony and leans into being the trust layer, not another assistant.

## 4. The repurpose

| | Yesterday (0.5xx) | The next three years |
|---|---|---|
| **Identity** | "Portable project truth and continuity tool." | **The trust & continuity substrate for AI-built software.** |
| **Primary user** | An AI model told to "Run Forge." | **Any agent, of any vendor**, plus the human who has to trust it. |
| **Primary surface** | A `python3 forge.py` CLI a human types. | **An agent-callable capability** (MCP / tool) invoked automatically, *and* the CLI. |
| **Core value** | Maps and records project facts. | **Refuses false certainty; carries verified truth across models, agents, and time.** |
| **Success metric** | Feature coverage, module count. | A cold model of *another vendor* can enter, work, and hand off with zero invented authority and zero lost truth. |

The tagline evolves from *"portable project truth and continuity that works with
any AI model"* to:

> **Forge — the trust layer for AI-built software. Provable truth, portable
> continuity, and honest hand-offs across any model, any agent, any year.**

## 5. What dies, what lives

**Dies (the ceremony):**
- The dozens of coupled `adopt --record-*/--retire-*` sub-flags collapse into a
  small, uniform `enabled / reason / scope / evidence` record. (Roadmap P1-05.)
- Overlapping release / evidence / rollback / authority services fold into the one
  project-truth boundary. (P1-04.)
- Historical and explanatory-only docs leave "required reading" for `reference/`.
  (P1-03.)
- The seven-axis percentage roadmap: already retired at 0.551. Stays dead.
- Any module made unreachable by a completed fold gets removed — *only after* the
  fold, never on reachability alone. (P1-06.)

**Lives (the durable core):**
- The `NOT_RUN`-is-not-`PASS` refusal, and every guardrail that enforces it.
- Exact identity, authority baseline, lineage, evidence binding.
- One-command continuity (Run Forge → Brief → work → clean Session Close).
- The vendor-neutral continuity kernel (G3) that stores *truth*, not model
  instructions, and preserves unknown fields through forward migration.
- Self-verification: the code and its story cannot silently diverge.

**Is added (the future-proofing):** an agent-native invocation path so "Run Forge"
becomes something agents *call*, not only something humans *type*. This is the
single highest-leverage move for 2029 relevance. See `ROADMAP-2029.md`.

## 6. The one honest caveat

Forge earns its keep only if it stays a *thin, boring, trustworthy* layer. The
failure mode is scope creep — Forge trying to become a coding agent, a prompt
governor, or a substitute for model intelligence. The product boundary in
`ROADMAP.md` forbids exactly this, and it must be defended in every future chunk.
A newer model may simplify or replace assistance-oriented code freely; it must
never be allowed to weaken exact historical truth, evidence identity, or migration
meaning.

Save it. Shrink it. Point it at the trust problem. Then let three years of smarter
models lean on it instead of around it.

*— Written at the 0.552 → 0.553 boundary. The certified 0.552 base is preserved
unchanged; this is the direction, not a mutation of the sealed record.*
