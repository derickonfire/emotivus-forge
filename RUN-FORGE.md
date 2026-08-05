# Run Forge

## The only first instruction

> **Run Forge.**

## What the active AI must do

1. Identify and safely extract the target project’s complete working source.
2. Extract this Forge ZIP so `Emotivus-Forge/` sits beside the target application inside the working root.
3. Work from the target-project root, not from inside Forge.
4. Run Forge with no command:

```bash
python3 Emotivus-Forge/forge.py
```

Windows fallback:

```bat
Emotivus-Forge\forge.cmd
```

5. Read `.forge/resume.md` before changing project files.
6. Report uncertainty, blockers, truth state, verification tier, the exact objective, the exact next action, and the exact Check scope honestly. Never describe `NOT_RUN` or blocked evidence as explained or passing. When JSON includes `ai_notice.speak: true`, append exactly one line in the form `Forge — <summary>`.
7. When Run Forge includes `recommended_prompt`, show it as one copy-ready line in the form `**Forge recommends this prompt —** <text>`. Do not strengthen it, bypass project authority, or copy full local evidence into the response.
8. At the end of meaningful work, explicitly close the session through Check so the next agent receives completed work, decisions, risks, evidence, and the exact next action. Respect Session Close preflight errors and warnings.


## Forge self-development layout

When Forge develops Forge, the development source is the target project and the exact public runtime
is a separate nested directory:

```text
Emotivus-Forge-Project/
├── FORGE-MANIFEST.json
├── emotivus_forge/
├── tests/
└── Emotivus-Forge/
```

Run `python3 Emotivus-Forge/forge.py` from `Emotivus-Forge-Project/`. Running `python3 forge.py`
from the development source root incorrectly uses that source root as the runtime and leaves no host
project beside it. The nested runtime should be excluded from ordinary target-project orientation.

## What Run Forge does

Run Forge performs one bounded active project-intelligence pass, normally targeting one to five minutes, then becomes passive. Internally it may use Progressive Adopt, Resume, or a scoped Quick Check as needed, but the user should receive one coherent Forge Brief rather than lifecycle ceremony.

The active pass covers exact identity, continuity and authority, optional distilled session intent, changed scope, safe checks, request/claim/code/evidence reconciliation, and one exact next action.

After the Brief, Forge remains passive until a meaningful checkpoint, package import, migration, unexpected mutation, Session Close, or Ship request.


## Optional session review

When the active AI has access to the current conversation, it may create a transient `forge-session-context/1` digest outside the project tree and pass it through `--session-context`. Forge rejects raw message or transcript fields and does not retain the digest. AI completion claims remain unverified until separate code and evidence support them.

## What Forge never does automatically

- Ship or deploy;
- delete files or data;
- execute production migrations;
- repair an environment;
- run an unapproved or fingerprint-changed native command;
- advance an existing observed checkpoint during Adopt refresh;
- infer project authority from a passing Check, native gate, existing artifact, or legacy snapshot;
- activate advanced or vaulted capability;
- convert a scoped Check into a project-level PASS;
- infer or submit Session Close automatically;
- infer safety guardrails or project events from prose, choose project versions, or silently weaken a recorded authority contract.

## Public commands

Help, Adopt, Resume, Check, and Ship remain the complete public interface. Authority confirmation, exact-fingerprint project-tree baseline authorization, and native-gate approval are controlled options under Adopt. Baseline authorization must be a separate operation and invalidates any earlier candidate checkpoint. Session Close is an explicit Check option. Project-owned identity, governed continuity registers, atomic guardrails, event obligations, confirmed project events, Ledger assertions, check qualifications, and field-trial plans are recorded or retired through Adopt. Ledger assertions and guardrails are evaluated automatically by Check; native evidence is mapped to qualified, unqualified, or stale detector status; field observations require explicit Session Close and a project-owned observation file. Raw native evidence is created only after explicit native execution.

## Notice restraint

The `Forge —` line is an evidence-backed interaction receipt, not advertising. Do not show it for no-op reads, do not repeat the same notice ID, and do not strengthen its claim.

## Native authority

Run Forge must respect the registered native execution mode. It may execute only a `forge-authorized` current fingerprint after explicit request. Owner-only, external-CI, and evidence-import-only gates remain external; matching evidence may be imported explicitly.

## Authority baseline

Run Forge must keep the observed checkpoint and the explicit project-authority baseline separate. Adopt refreshes orientation without absorbing intervening edits. Check prints the complete current fingerprint for review. Only a separate `Adopt --authorize-baseline` operation may accept that exact tree, and the unchanged tree must then pass `Check --checkpoint` again. Until that operation exists, a clean aggregate Check is `NOT_RUN`, never PASS; component observations remain visible and real defects still FAIL. Quarantined changes remain visible even after the ordinary observed checkpoint advances. Forge does not authenticate the named authority or prove authorship.

## Guided next step

The recommended prompt exists for non-technical users who should not have to translate a Resume packet into agent instructions. It is bounded workflow guidance, not authority to code through a blocker, run an owner-only gate, resolve a decision fork, or claim release readiness.

## Ship claim readiness

`forge ship .` remains blocked for release. It may report a lower cumulative claim only when every prior level passes. Never translate continuity-ready, checkpointed-candidate, authority-recorded-candidate, lineage, migration, package-family, surface, native, release-fact, runtime, or persisted-state claims into release approval.

## Persisted-state transition evidence

Forge may record project-owned state-transition plans and compare owner or external-CI testimony against exact before/after fixtures, deployment artifact bytes, migration bytes, receipts, and same-Check Runtime Proof. It does not perform deployment, migration, restoration, rollback, or semantic database validation. Missing evidence remains `NOT_RUN`; disagreement blocks Check. Detailed fixtures and receipts remain local so routine AI context stays compact.

## Governed continuity

Run Forge should use the current project-owned continuity register when present. Owner-declared and project-evidenced facts outrank developer, agent, and automatic records. Changed support becomes stale; it is not silently rewritten. Open knowledge gaps remain visible until resolved or explicitly retired. Resume carries only compact current facts, gaps, source references, and the exact next action—not a complete conversation archive.

## Session sidecar

Forge records a compact observational mode in existing `state.json`: development, evidence analysis, or release assessment. The sidecar does not monitor this chat, run in the background, authorize changes, or intercept model traffic. Consequential operations remain explicit through the five public commands.

## Returned external evidence

Portable evidence and owner-attestation kits may package exact allowlisted return ZIPs. Review those
returns from Forge source with `tools/review_external_evidence.py` against the exact original sealed
kit. A passing review verifies bounded technical semantics only. It never authenticates the reviewer,
owner, operators, administrative independence, or provider report, and it never creates release
authorization or release readiness. See `docs/EXTERNAL-EVIDENCE-REVIEW.md`.
