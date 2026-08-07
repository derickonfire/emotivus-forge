# LineCheck Dual-AI Collaboration Protocol

**Document status:** Final two-model consensus; pending Rox’s ratification and activation  
**Protocol version:** 0.2  
**Prepared:** 2026-08-06  
**Reconciles:** `CLAUDE-RESPONSE-DUAL-AI-PROTOCOL-v0.1.md`, `CLAUDE-REVIEW-PROTOCOL-v0.2.md`, and fresh live-repository checks  
**Project owner and final arbiter:** Rox  
**Primary project repository:** `derickonfire/linecheck-acceptance`  
**Separate Forge repository:** `derickonfire/emotivus-forge`  
**Intended users:** Rox, ChatGPT/OpenAI coding sessions, Claude/Claude Code sessions, and any future AI coding model admitted by Rox

---

## 0. How to use this document

Give this entire file to both the ChatGPT and Claude sessions.

Each session must:

1. Read this document completely.
2. Refresh the live LineCheck repository before relying on any mutable version, branch, roadmap, acceptance, release, CI, or ownership statement in this document.
3. Record `observed_at`, the exact `origin/main` SHA, the active task branch, and the CI verdict being relied on.
4. State its identity, proposed role, exact base commit, task claim, write scope, and reviewer before editing.
5. Treat GitHub—not either chat transcript—as the shared coordination channel.
6. Stop and involve Rox when the live repository contradicts this document, the other model, or itself.
7. Use the full declaration and task contract for implementation or release-sensitive work; use the short declaration for planning-only or non-authoritative documentation work.
8. Never claim to be monitoring, scheduled, or working in the background unless a real automation or scheduled task actually exists, was disclosed to Rox at creation, and can be cancelled on request.

This document is a **collaboration constitution and operating procedure**. It is not a release receipt, acceptance result, roadmap completion claim, or substitute for the repository’s current release authority.

All repository snapshots in this document expire immediately when `origin/main`, the relevant task branch, the governing authority, or the controlling CI run changes.

# 1. Executive decision

## 1.1 Recommended operating model

LineCheck should use a **builder–reviewer model with adaptive specialization**, not two autonomous AIs editing the same source at once.

For each bounded task:

- one model is the **Task Owner**;
- the other model is the **Independent Reviewer**;
- both work from an explicitly recorded base commit;
- only the Task Owner edits the task branch;
- the reviewer reproduces evidence and reviews the exact diff;
- Rox resolves contention, approves material role changes, and authorizes merges when repository controls cannot enforce them automatically.

Parallel development is allowed only when tasks have separate branches or worktrees and non-overlapping write scopes.

## 1.2 My strongest recommendation

Do **not** begin this experiment with two feature builds in parallel.

First restore one trustworthy, green, internally consistent baseline through **LC-001 — Authority, web-doc, and mirror reconciliation**:

- reconcile the successful exact-source `v0.19.176+r3` evidence with the contradictory live release authorities;
- diagnose the exact-source receipt-binding failure on the current `main` head;
- reconverge the duplicated `build_web_doc.py` tools byte-for-byte;
- regenerate and verify `web-doc.zip` and its manifest from the intended source of truth;
- use a task branch, draft pull request, exact-head gate, independent Claude review, and Rox-controlled merge;
- freeze new `v0.19.177` product implementation until that task establishes a green and truthful baseline.

This tests the protocol on a small, real, high-contention repair rather than on speculative process paperwork.

## 1.3 Why this structure

The practical advantage of two models is not simply “twice as much code.” It is:

- different failure detection patterns;
- specialization by task;
- independent review;
- explicit challenge of assumptions;
- reduced dependence on one session’s memory;
- a controlled way to transfer work when one model is better suited.

The danger is duplicated work, silent conflict, stale repository context, gate weakening, and false consensus. Git isolation, task contracts, evidence, and owner escalation are therefore more important than model branding.

---

# 2. Confirmed repository boundaries and observed state

## 2.1 Repository independence

### LineCheck

- Repository: `derickonfire/linecheck-acceptance`
- Default branch: `main`
- Visibility observed during review: private
- Purpose: LineCheck application, planning, acceptance, release evidence, commercial documentation, toolset, and packaging

### Emotivus Forge

- Repository: `derickonfire/emotivus-forge`
- Default branch: `main`
- Visibility observed during review: public
- It remains a separate experimental project and has no LineCheck write authority.

Their roadmaps, release identities, source trees, issues, branches, permissions, and acceptance claims must remain separate.

## 2.2 Dated live snapshot used for v0.2

**Observed at:** 2026-08-06 13:11 America/New_York  
**Observed `main` head:** `bcbf9a9a075366a14a5a5fcdb443cd03ae97becf`  
**Head commit title:** `Synchronize v0.19.177 web documentation package`

The repository contains credible evidence that `v0.19.176+r3` passed its controlled runtime gate on commit `50bc5a563d97e67b8ed023224b45b872e5882716` in workflow run `31099038434`.

The current head is nevertheless **verified red**:

- workflow run `31119008933` targets exact head `bcbf9a9a075366a14a5a5fcdb443cd03ae97becf`;
- attempt 1 was interrupted by a GitHub Actions service outage before meaningful execution;
- attempt 2 completed with conclusion `failure`;
- all 80 acceptance groups passed with `80 PASS · 0 FAIL · 0 SKIP`, including 742 real-MariaDB assertions, 216 page executions with 0 fatals, and Chromium PWA PASS;
- exact-source receipt verification then failed on three manifest hash mismatches: `Release/RELEASE-STATE.json`, `toolset/tools/build_web_doc.py`, and `web-doc.zip`;
- `MANIFEST-SHA256.txt` had not been regenerated after the post-r3 changes, so the exact head has no accepted receipt and remains red.

A previous outage narrative does not supersede the completed exact-head failure.

## 2.3 Live authority contradiction

The current release authorities do not agree:

### `Release/RELEASE-STATE.md`

It identifies `v0.19.176+r3` as an **acceptance candidate**, states Routine `44/49`, names `v0.19.175` as the last accepted phase, and says `v0.19.177` must not begin until the exact r3 receipt is accepted.

### `Release/RELEASE-STATE.json`

It still declares:

- `release_status: acceptance_candidate`;
- `previous_accepted_boundary: v0.19.175+r14`;
- null current source-commit and manifest bindings.

But its `routine` object simultaneously declares:

- an accepted `v0.19.176` completed boundary;
- `completed_phases: 45`;
- `next_version: 0.19.177`;
- `percentage: 91.8`.

This is an internal authority contradiction, not merely a stale paragraph.

## 2.4 Relevant commit sequence

Claude’s response identified this post-r3 sequence, which the live history supports:

1. `8ace7f3` — prepare the `v0.19.177` Routine phase-45 state;
2. `1980aab` — change the web-documentation generator to read Routine progress from release state;
3. `bcbf9a9` — regenerate `web-doc.zip`.

The sequence explains the previously mysterious `v0.19.177` package commit. It does **not** by itself prove that every higher authority was promoted consistently or that the current head is acceptable.

## 2.5 Confirmed mirror divergence

The repository currently contains two different implementations of the same shared generator:

- `site/tools/build_web_doc.py` retains default Routine progress of `44/49`;
- `toolset/tools/build_web_doc.py` reads Routine progress from `Release/RELEASE-STATE.json` and currently resolves `45/49`.

They are not byte-identical. This creates competing package-generation behavior and must be repaired under the mirror invariant.

## 2.6 Current safe classification

Until LC-001 is accepted:

- successful controlled evidence exists for r3 on `50bc5a5`;
- the repository’s current release authorities remain contradictory;
- the current `main` head is red;
- `v0.19.177` feature implementation is frozen;
- no model may declare the project globally accepted, activate a new phase, or rewrite the contradiction from memory alone.

The first task must determine the intended authoritative state, preserve the accepted evidence if valid, reconverge the generator mirrors, regenerate the package and source manifest deterministically, and produce a green exact-head receipt.

## 2.7 GitHub governance state observed

During review:

- there were no open pull requests;
- `main` was unprotected;
- the runtime workflow executes on pushes and pull requests;
- it binds receipts to `GITHUB_SHA` and retains artifacts.

This is strong application-level evidence with a weak merge-control boundary. The direct-push sequence and red `main` demonstrate why branch protection or an immediate manual no-direct-push regime is the first governance priority.

## 2.8 Existing Forge-named marker inside LineCheck

LineCheck’s existing `site/tools/run_all_checks.sh` emits `FORGE_CHECK`, `FORGE_STATUS`, `FORGE_EXECUTED`, `FORGE_SKIPS`, and related evidence markers. The script describes this as a `Forge 1.0.5 marker protocol`.

This is existing historical naming inside LineCheck. It is not evidence that the separate Forge repository is installed, authoritative, or helpful.

Until Rox, ChatGPT, and Claude review it:

- freeze the existing marker behavior;
- do not deepen it;
- do not silently remove or rename it;
- do not treat `FORGE_STATUS: PASS` as proof that Forge contributed;
- do not add any cross-repository write path.

## 2.9 Snapshot and verdict precedence

For mutable facts:

1. refresh the repository and CI;
2. record `observed_at`, exact SHA, run ID, and attempt number;
3. prefer a completed exact-head verdict over an earlier pending, cancelled, or outage narrative;
4. distinguish **test evidence** from **repository authority**—a green run does not repair contradictory release documents by itself;
5. require the exact CI run plus retained receipt and independent receipt verification for acceptance claims;
6. mark copied snapshots stale as soon as the branch, authority, or run changes.

# 3. Authority hierarchy

When sources disagree, use this hierarchy.

## 3.1 Priority and product authority

1. **Rox’s explicit, current decision**
   - Controls product intent, priorities, acceptable tradeoffs, role assignments, and whether work may proceed.
   - A decision should be written into the repository when it changes enduring project truth.

2. **Current repository release entrypoint**
   - `Release/START-HERE.md`

3. **Current release state**
   - `Release/RELEASE-STATE.md`
   - `Release/RELEASE-STATE.json`

4. **Current phase contract and continuation authority**
   - the exact files named by `START-HERE.md`;
   - for the observed snapshot:
     - `Planning/ROUTINE-SCHEDULE-INTEGRATION-AND-WEB-PWA-ACCEPTANCE-CONTRACT-v0_19_176.md`;
     - `Planning/ROUTINE-CONTINUATION-v3.md`.

5. **Exact controlled evidence**
   - completed GitHub Actions run on the exact claimed SHA;
   - exact commit and tree;
   - retained receipt and log;
   - artifact ID and digest;
   - independent `verify_receipt.py` result against the same source;
   - the run-and-receipt pair is the empirical proof of acceptance, while synchronized authority files record what that proof means for the roadmap.

6. **Current executable source and tests**

7. **Accepted decision records and task contracts**

8. **Handoff and session summaries**

9. **Chat transcripts, model memory, prior prompts, and this document’s snapshot**
   - Useful context only.
   - Never sufficient to declare a release, schema, migration, roadmap phase, or acceptance result.

## 3.2 Important qualification

Rox can change the project’s goals and can authorize exceptions. Neither Rox nor an AI should relabel a failing or unexecuted test as passing. Product authority and empirical evidence have different jobs.

## 3.3 Conflict rule

When two sources at the same level disagree, or a lower source appears newer than a higher source:

1. stop the disputed action;
2. preserve both facts;
3. identify exact file paths, commits, timestamps, and evidence;
4. ask the other model for an independent reading;
5. escalate to Rox if the contradiction remains;
6. record the resolution in the repository.

No model may resolve a contradiction by deleting the inconvenient source first.

---

# 4. Goals and non-goals

## 4.1 Goals

The collaboration system should:

- preserve one authoritative LineCheck truth;
- let ChatGPT and Claude contribute according to demonstrated strengths;
- allow roles to change without politics or silent takeovers;
- isolate parallel work;
- make every task claim, handoff, review, and disagreement inspectable;
- use independent review rather than duplicated confidence;
- keep Rox informed without requiring Rox to mediate ordinary implementation details;
- measure whether Forge contributes value;
- prevent Forge from becoming an unreviewed authority;
- reduce stale-session errors and context erosion;
- preserve LineCheck’s exact acceptance and release discipline.

## 4.2 Non-goals

This protocol does not:

- make either AI autonomous project owner;
- allow the models to merge directly to `main`;
- allow both models to edit one branch or worktree;
- create a general agent orchestration platform;
- place chat transcripts in the repository;
- duplicate the full roadmap or release state in collaboration files;
- make Forge a required dependency;
- permit one AI to approve its own release work;
- replace runtime evidence with model consensus;
- authorize production deployment;
- assume ChatGPT and Claude can directly read each other’s private chat sessions.

---

# 5. Fundamental rules

## Rule 1 — Optimize for LineCheck, not for a model

No task belongs permanently to ChatGPT or Claude. It belongs to the model best positioned to complete it safely, with the other model reviewing when practical.

## Rule 2 — One task, one owner, one reviewer

Every implementation task has exactly one active Task Owner and one named reviewer.

## Rule 3 — GitHub is the shared message bus

The models do not share hidden memory. Durable coordination must appear in:

- a task contract;
- a branch or worktree;
- commits;
- a draft pull request;
- review comments;
- a handoff file;
- a decision record.

A statement made only in one chat is not a handoff.

## Rule 4 — No shared writable worktree

ChatGPT and Claude must never edit the same local checkout concurrently.

## Rule 5 — Exact base before work

Every task records its base commit SHA. “Latest main” is not an acceptable permanent identifier.

## Rule 6 — Live truth beats copied context

At each session start, before review, and before merge, refresh and reread the live authority. Record `observed_at`, exact SHAs, and the controlling CI run. A snapshot without those bindings is context, not truth.

## Rule 7 — No silent overlap

A model must not touch files outside the task’s declared write scope without updating the contract and notifying the reviewer.

## Rule 8 — No silent role takeover

A model may propose a transfer. It may not assume the other model’s task because it believes it can do better.

## Rule 9 — Evidence over narrative

Use diffs, tests, exact commands, receipts, screenshots when relevant, and reproducible failure cases. Confidence language is not evidence.

## Rule 10 — No gate weakening disguised as a fix

Changes to checks, expected counts, SKIP handling, fixtures, timing, retries, browser behavior, receipt parsing, or acceptance language are high-risk and require explicit review.

## Rule 11 — No roadmap advance before acceptance

A phase is not complete because code exists. It is complete only when the governing contract’s evidence exists and the authority is updated consistently.

## Rule 12 — Disagreement is useful data

Dissent must be preserved and escalated, not averaged away.

## Rule 13 — The reviewer must remain independent

The reviewer may suggest patches, but should not quietly become co-author of the same branch. If substantial implementation work transfers, record a role transfer.

## Rule 14 — Keep the collaboration layer small

Collaboration files should point to release truth, not restate it. The system should reduce context duplication, not create a second bureaucracy.

## Rule 15 — Preserve mirror invariants

When a shared tool intentionally exists in both `site/tools/` and `toolset/tools/`, every task that changes one must inspect and update the other. The task contract must name both copies, focused evidence must compare them byte-for-byte where equality is required, and a commit may not knowingly leave one stale.

## Rule 16 — Completed exact-head verdicts supersede pending narratives

A completed run on the exact head supersedes an earlier outage, queued rerun, or pending description. A failed run keeps the head red. A green run proves only what its receipt and contract prove; it does not silently reconcile release authority.

## Rule 17 — No invisible background work

Neither AI may claim that it is monitoring, scheduled, checking later, or continuing in the background unless a real automation or scheduled task actually exists, was disclosed to Rox at creation, and can be cancelled on request. Claiming monitoring that no mechanism performs is fabrication. Otherwise the model must perform the check in the current session or state that no future check is active.

---

# 6. Default roles

These are starting defaults based on Rox’s requested division. They are **tie-breakers only** and never permanent identities.

Every task contract assigns roles afresh using task type, current context, available tools, demonstrated evidence quality, and workload. A model does not inherit ownership merely because a task resembles its default area.

## 6.1 ChatGPT default lead areas

ChatGPT normally leads:

- product and user-flow coherence;
- frontend architecture;
- visual hierarchy and interaction design;
- responsive behavior;
- accessibility review;
- copy, terminology, and information architecture;
- commercial-site and product-documentation consistency;
- cross-file roadmap and release-document consistency;
- packaging clarity and owner-facing handoff quality;
- acceptance-contract review from the user-facing perspective;
- task decomposition and collaboration coordination.

## 6.2 Claude default lead areas

Claude normally leads:

- backend PHP and service-layer implementation;
- database schema, migrations, concurrency, and transactional correctness;
- authorization and security-boundary debugging;
- acceptance harnesses;
- CI and controlled gate execution;
- error isolation and root-cause analysis;
- performance and reliability investigation;
- test design and negative-path coverage;
- receipt verification and exact-source checks;
- large refactors where dependency tracing is central.

## 6.3 Shared areas

Either model may lead:

- architecture;
- security review;
- API contracts;
- PWA behavior;
- documentation;
- test design;
- release readiness;
- debugging;
- code review.

The assignment depends on task evidence, current context, and workload.

## 6.4 Role labels

Use these labels:

- **Owner** — writes and is accountable for the task branch.
- **Reviewer** — independently evaluates the exact branch and evidence.
- **Consulted** — gives bounded advice without writing the task branch.
- **Rox/Arbiter** — resolves scope, product, risk, and contention.
- **Forge/Advisory** — optional evidence or continuity input with no authority.

## 6.5 Capability is measured, not presumed

After each milestone, compare:

- defects found after handoff;
- review corrections;
- CI failure rate;
- rework;
- scope violations;
- time spent resolving misunderstandings;
- quality of evidence;
- owner intervention required.

Use those results to adapt the role matrix.

---

# 7. Role-transfer protocol

Either model may propose a transfer at any time before merge.

## 7.1 Valid reasons

- the task moved outside the current owner’s strongest area;
- the owner lacks a required runtime or tool;
- the reviewer found a deeper issue that changes task type;
- the current owner is blocked;
- the other model has materially better context;
- parallel work created a dependency that should be consolidated;
- the task’s risk profile changed.

## 7.2 Transfer proposal template

```md
## ROLE-TRANSFER PROPOSAL

Task ID:
Current owner:
Proposed owner:
Current reviewer:
Proposed reviewer:
Base commit:
Current branch:
Reason for transfer:
Completed work:
Uncommitted work:
Files already changed:
Remaining scope:
Known risks:
Tests already run:
Evidence location:
Recommended next action:
Does this change the accepted task contract? Yes/No
Does this touch a release, schema, migration, gate, or Forge boundary? Yes/No
```

## 7.3 Allowed responses

The other model must answer with one of:

- `ACCEPT`
- `ACCEPT WITH CONDITIONS`
- `COUNTERPROPOSE`
- `DECLINE — ESCALATE TO ROX`

## 7.4 Transfer completion

A transfer is complete only when:

- both models agree, or Rox decides;
- the task contract is updated;
- the branch and worktree are identified;
- all work is committed or explicitly discarded;
- the new owner confirms the exact base and diff;
- the new reviewer confirms independence.

## 7.5 Contention

If both models want ownership and neither yields, they must not both implement competing hidden branches by default. Submit a short contention report to Rox.

Rox may choose:

- one owner and one reviewer;
- two explicit prototypes with a comparison contract;
- a narrower task split;
- postponement;
- a human decision on architecture.

---

# 8. Git and worktree operating model

## 8.1 Preferred topology

Use one read-only coordination clone and separate linked worktrees when the models operate on the same machine.

Example:

```bash
git clone git@github.com:derickonfire/linecheck-acceptance.git linecheck-coordination
cd linecheck-coordination

git fetch origin --prune
git switch main
git pull --ff-only

BASE_SHA="$(git rev-parse origin/main)"
echo "$BASE_SHA"

git worktree add ../linecheck-chatgpt-LC-001 \
  -b ai/chatgpt/LC-001 "$BASE_SHA"

git worktree add ../linecheck-claude-LC-002 \
  -b ai/claude/LC-002 "$BASE_SHA"

git worktree list
```

If the models operate in separate cloud or desktop environments, each must still:

- fetch immediately before task start;
- branch from the same recorded base when tasks are related;
- use distinct branch names;
- push before requesting review.

## 8.2 Branch naming

```text
ai/chatgpt/<task-id>-<short-slug>
ai/claude/<task-id>-<short-slug>
review/chatgpt/<task-id>
review/claude/<task-id>
repair/<release-id>-<short-slug>
```

Examples:

```text
ai/chatgpt/LC-201-pwa-copy-review
ai/claude/LC-202-runtime-receipt-hardening
repair/v0.19.176-r3-release-state
```

## 8.3 Branch rules

- Branch from a recorded commit.
- One active task per branch.
- Never force-push after review starts.
- Never amend reviewed commits unless the reviewer agrees to restart review.
- Never push directly to `main`.
- Never merge a branch whose base or head is ambiguous.
- Use `git status --short` before and after work.
- Leave the worktree clean.
- Prefer small, intentional commits.
- Do not mix formatting, refactoring, generated files, and behavior changes without explicit scope.
- Do not delete other AI branches without Rox’s authorization.

## 8.4 Worktree cleanup

After a merged or abandoned task:

```bash
git worktree remove ../linecheck-chatgpt-LC-001
git branch -d ai/chatgpt/LC-001
git fetch origin --prune
git worktree prune
```

Do not clean up until the handoff, review, and evidence are retained.

## 8.5 Rebase and moving-base rule

When `main` changes during a task:

1. fetch;
2. compare the task base to the new `origin/main`;
3. inspect whether authority, schema, manifests, gate code, or task files changed;
4. notify the reviewer;
5. rebase or merge only after deciding whether the task contract remains valid;
6. rerun affected evidence;
7. update the recorded base and head SHAs.

A model may not say “only documentation changed” without inspecting the exact diff.

---

# 9. Proposed repository collaboration layer

Do not add these files until Rox approves. Once approved, use one dedicated governance branch and pull request. Create only the files needed immediately.

```text
/
├── AGENTS.md
├── CLAUDE.md
├── REVIEW.md
├── .github/
│   ├── CODEOWNERS
│   └── PULL_REQUEST_TEMPLATE.md
└── Planning/
    └── AI-COLLABORATION/
        ├── README.md
        ├── TASK-BOARD.md
        ├── DECISIONS.md
        └── HANDOFFS/
            └── README.md
```

Defer `COLLABORATION-HEALTH.md` until the first milestone health check and defer `FORGE-EVALUATION.md` until the first authorized Forge use. The templates remain in this protocol until then.

## 9.1 Enforcement before ceremony

Before adding convenience files:

1. enable protected-main rules when the GitHub plan permits; or
2. immediately adopt the manual no-direct-push regime in §19.4;
3. require draft pull requests and the runtime gate for LC-001;
4. let Rox perform merges until enforcement is proven.

A convention file cannot stop an unreviewed direct push.

## 9.2 `AGENTS.md`

Purpose:

- model-neutral instructions;
- authority order;
- safe commands;
- required tests;
- mirror invariants;
- branch and pull-request rules;
- forbidden actions;
- pointers to current release authority.

Keep it concise. Do not duplicate the roadmap or a dated release snapshot.

## 9.3 `CLAUDE.md`

Purpose:

- make Claude Code load the shared collaboration rules;
- point to `AGENTS.md` rather than forking it;
- add only Claude-specific operational notes.

Suggested beginning:

```md
# Claude Code instructions for LineCheck

Read `AGENTS.md` first and obey it as the shared model-neutral contract.
Read `Release/START-HERE.md` and the active collaboration task record.
Do not edit until the required declaration and task claim exist.
Do not use `--dangerously-skip-permissions`.
Do not share a writable branch or worktree with another model.
```

Instruction files are context, not an enforcement boundary. Security-critical rules require GitHub controls, permissions, tests, and human review.

## 9.4 `REVIEW.md`

Define review severity, release/gate review, negative-path review, mirror checks, and blocker classification. Do not duplicate general architecture truth.

## 9.5 `TASK-BOARD.md`

Contain only active claims and a short archive index. It must not become a second roadmap.

## 9.6 `DECISIONS.md`

Use append-only records for collaboration and cross-cutting architecture decisions. Mark superseded decisions; do not rewrite history.

## 9.7 Deferred records

Create a health-check record only when a milestone produces one. Create a Forge-evaluation record only when Forge is actually used. Empty templates are not progress.

## 9.8 Avoid context inflation

Do not store full chat transcripts, repeated release state, long model self-evaluations, every terminal command, or speculative ideas as commitments. Use paths, SHAs, run IDs, receipt IDs, and concise evidence.

# 10. Mandatory session-start protocol

Every ChatGPT or Claude session that may affect the repository begins with a live refresh and a proportionate declaration.

## 10.1 Repository refresh

```bash
git status --short
git remote -v
git fetch origin --prune
git rev-parse origin/main
git log -1 --format='%H%n%ci%n%s' origin/main
```

Do not pull over uncommitted work.

## 10.2 Read authority in order

1. `Release/START-HERE.md`
2. `Release/RELEASE-STATE.md`
3. `Release/RELEASE-STATE.json`
4. every planning/contract file named by `START-HERE.md`
5. `Release/VERIFICATION.md`
6. `Release/OWNER-CHECKLIST.md`
7. active task board and handoff
8. relevant workflow, generators, mirrors, and test code

## 10.3 Check collaboration state

Inspect active branches, open pull requests, review threads, task claims, recent `main` changes, overlapping paths, exact-head CI, and any changed authority or generator since the handoff.

## 10.4 Full Session Declaration

Required for implementation, release, schema, migration, gate, package, manifest, security, authorization, or Forge-sensitive work:

```md
## SESSION DECLARATION

Observed at:
Model/session:
Requested role:
Task ID:
Task goal:
Repository:
Base branch:
Base commit:
Observed origin/main:
Worktree path or environment:
Task branch:
Planned write scope:
Read-only dependency scope:
Named reviewer:
Current accepted release:
Current candidate:
Current roadmap boundary:
Required acceptance contract:
Controlling CI run/attempt/verdict:
Known repository contradictions:
Mirror pairs affected:
Forge involvement proposed: None / Read-only advisory / Other
Destructive or production access required: No
First evidence to reproduce:
```

## 10.5 Short Session Declaration

Allowed only for planning-only or non-authoritative documentation work with no code, release-state, package, manifest, gate, or product-truth edits:

```md
## SHORT SESSION DECLARATION

Observed at:
Model/session:
Task:
Observed origin/main:
Write scope:
Named reviewer:
Repository actions authorized: None / Specify
```

A planning-only task does not consume a LineCheck application version.

## 10.6 Stop conditions at startup

Do not edit when:

- `git status` is unexpectedly dirty;
- the base differs from the handoff and the diff is unreviewed;
- release authorities disagree;
- the exact head is red and the task does not explicitly own its repair;
- the task is already claimed or ownership is unclear;
- overlapping write scopes exist;
- production credentials or live data would be needed;
- the task requires weakening a gate to hide a failure;
- a mirror would be left stale;
- Forge involvement exceeds the approved boundary.

# 11. Task contract

Every implementation task must have a contract before code changes.

```md
# TASK CONTRACT

Task ID:
Title:
Status: Proposed / Claimed / In Progress / Review / Blocked / Accepted / Superseded
Owner:
Reviewer:
Requested by:
Repository:
Base commit:
Task branch:
Pull request:
Related release/phase:
Goal:
User-visible outcome:
Problem evidence:
In scope:
Out of scope:
Files allowed to change:
Files read-only:
Shared/high-contention files:
Acceptance criteria:
Required commands/tests:
Required controlled evidence:
Security/privacy considerations:
Migration/schema impact:
Accessibility impact:
Documentation impact:
Packaging/manifest impact:
Forge involvement:
Dependencies:
Known risks:
Rollback:
Escalation triggers:
Owner sign-off:
Reviewer outcome:
Rox decision:
```

## 11.1 Write-scope rule

The `Files allowed to change` field is binding.

When an unexpected file must change:

1. stop;
2. explain why;
3. update the contract;
4. notify the reviewer;
5. check for overlap;
6. proceed only when uncontested.

## 11.2 High-contention files

Treat these as serialized unless Rox approves a split:

- `Release/RELEASE-STATE.md`;
- `Release/RELEASE-STATE.json`;
- `Release/START-HERE.md`;
- `Release/VERIFICATION.md`;
- `Release/OWNER-CHECKLIST.md`;
- active continuation and acceptance contracts;
- `MANIFEST-SHA256.txt`;
- `web-doc.zip`;
- `.github/workflows/*`;
- `site/tools/run_all_checks.sh`;
- `site/tools/runtime-gate/*`;
- `site/tools/build_web_doc.py` and `toolset/tools/build_web_doc.py` as one serialized mirror pair;
- `site/tools/check_browser_pwa.py` and `toolset/tools/check_browser_pwa.py` as one serialized mirror pair;
- schema and migration authority;
- shared bootstrap, authorization, routing, and global layout files;
- global design tokens and shared CSS when both tasks touch UI;
- package generators and receipt parsers.

One model may implement while the other reviews. Do not parallel-write these files.

---

# 12. What can and cannot run in parallel

## 12.1 Usually safe with separate branches

- a bounded frontend component and an unrelated backend test;
- copy/accessibility review and a database investigation;
- commercial documentation and an isolated application service;
- read-only release audit and implementation in non-overlapping paths;
- separate prototypes explicitly requested by Rox;
- reviewer reproduction while the owner waits for feedback.

## 12.2 Requires dependency ordering

- backend contract before frontend integration;
- schema before data-access code;
- service changes before UI bindings;
- accepted application behavior before commercial claims;
- accepted source before package generation;
- exact package before final receipt verification.

## 12.3 Do not parallelize

- two edits to the same schema or migration;
- two implementations of the same acceptance fix unless Rox requests a bake-off;
- release-state activation and candidate-source mutation;
- manifest generation while source is changing;
- runtime-gate modification and its “independent” review by the same model;
- changes to shared authorization boundaries;
- two agents editing `web-doc.zip`;
- Forge integration and LineCheck release work in one task;
- direct changes to `main`.

---

# 13. Standard execution loop

## Step 1 — Reproduce

The Task Owner reproduces the current failure or establishes the current baseline before changing code.

## Step 2 — Map the contract

Identify:

- expected behavior;
- governing requirement;
- current implementation path;
- exact evidence that will distinguish success from failure;
- negative cases;
- affected release and documentation.

## Step 3 — Propose the smallest safe change

Prefer a narrow patch over broad cleanup.

Separate opportunistic refactors into later tasks.

## Step 4 — Implement with incremental commits

Example commit sequence:

```text
test: reproduce stale schedule edit acceptance gap
fix: make schedule update revision-bound
docs: synchronize schedule mutation contract
```

## Step 5 — Run focused evidence

Run the smallest relevant checks first. For shared mirrors, compare the intended pair explicitly. For harness, retry, timing, concurrency, browser, or determinism changes, a handful of green runs is not enough.

## Step 6 — Run required broader evidence

Run the task contract’s full required set. Never hide SKIPs.

Determinism validation must be risk-based and recorded. Use **dozens of consecutive passing runs** when the defect is intermittent; use a 50/50 bar when the observed failure rate, release risk, or governing precedent resembles the r3 browser-harness case. Record the chosen sample size and why it is sufficient. Repeated local passes do not replace the controlled exact-head gate.

## Step 7 — Prepare handoff

Commit, push, record exact head SHA, and provide the review packet.

## Step 8 — Independent review

The reviewer:

- checks the contract;
- reads the full diff;
- reproduces the issue where possible;
- runs required checks independently;
- looks for weakened assertions or changed expectations;
- checks documentation and release implications;
- records blockers and non-blockers.

## Step 9 — Resolve findings

The owner responds to every finding. The reviewer marks each as:

- resolved;
- accepted risk;
- owner decision required;
- still blocking.

## Step 10 — Controlled gate

Run CI and controlled evidence against the exact reviewed head.

## Step 11 — Merge decision

Rox or the authorized human verifies:

- exact head SHA;
- reviewer outcome;
- required status;
- unresolved contentions;
- release-state consequences.

## Step 12 — Post-merge verification

Refresh `main`, verify the merge, rerun any post-merge exact-source requirement, and update task status.

---

# 14. Handoff packet

```md
# AI HANDOFF

Task ID:
From:
To:
Role of recipient: Reviewer / New Owner / Consulted
Repository:
Base SHA:
Head SHA:
Branch:
Pull request:
Goal:
What changed:
Why:
Files changed:
Files intentionally not changed:
Behavioral impact:
Schema/migration impact:
Security/privacy impact:
Accessibility impact:
Documentation impact:
Packaging/manifest impact:
Tests run:
Exact results:
SKIPs or unavailable evidence:
Known limitations:
Unresolved questions:
Potential regressions:
Review focus:
Required next command:
Forge used: Yes/No
Forge value assessment:
Working tree clean: Yes/No
```

A handoff that says only “continue” is invalid.

---

# 15. Independent review protocol

## 15.1 Review responsibilities

The reviewer must:

- verify the exact base and head;
- inspect every changed file;
- confirm the change matches the task contract;
- check whether unrelated changes are present;
- evaluate user-facing behavior;
- test negative and authorization paths;
- inspect migration and rollback implications;
- verify no secret or personal data entered the repository;
- verify expected counts were not changed merely to match output;
- verify retries do not mask a product failure;
- verify fixtures still model production behavior;
- verify documentation names the true status;
- verify shared-tool mirror pairs remain byte-identical under Rule 15, or that the task contract explicitly documents an approved divergence;
- distinguish local evidence from controlled evidence;
- state what was not tested.

## 15.2 Review outcomes

Use one:

- `APPROVE`
- `APPROVE WITH NON-BLOCKING FOLLOW-UPS`
- `REQUEST CHANGES`
- `BLOCK — AUTHORITY CONFLICT`
- `BLOCK — EVIDENCE INCOMPLETE`
- `ESCALATE TO ROX`

## 15.3 Consensus definition

Consensus means:

- both models agree on the exact claim and evidence; or
- one model accepts the other’s decision with recorded reservations; or
- Rox resolves the disagreement.

Silence, lack of response, or two optimistic summaries is not consensus.

## 15.4 No reciprocal rubber-stamping

The reviewer must not approve because:

- the other model is usually good at that area;
- CI is green but the contract is wrong;
- a large diff is difficult to inspect;
- the task “looks done”;
- the release is behind schedule;
- Forge reported PASS.

---

# 16. Contention and escalation

## 16.1 Immediate escalation triggers

Escalate when:

- both models claim the same task;
- role transfer is disputed;
- architecture choices conflict;
- release files disagree;
- current `main` contradicts the roadmap;
- a branch appears to advance a forbidden phase;
- a gate change could reduce coverage;
- a migration or data repair is ambiguous;
- production or personal data may be involved;
- one model wants Forge integration and the other objects;
- a model wants to bypass tests, permissions, review, or exact-source verification;
- the reviewer cannot reproduce the owner’s evidence;
- a merge would overwrite another active branch’s work.

## 16.2 Contention report

```md
# ROX DECISION REQUIRED

Topic:
Task ID:
Affected repository:
Current accepted state:
Disputed action:
ChatGPT position:
Claude position:
Facts both agree on:
Evidence:
Files/commits involved:
Risk of proceeding:
Risk of waiting:
Options:
1.
2.
3.
Recommended default if no decision:
Work frozen:
Unrelated work that may continue:
```

## 16.3 Freeze scope

Freeze the smallest safe scope.

Freeze the full release when the disagreement affects:

- release identity;
- schema;
- migration;
- authorization;
- acceptance gate;
- manifest;
- exact-source evidence;
- production deployment;
- Forge integration.

## 16.4 Rox’s response format

```md
ROX DECISION:
Chosen option:
Required changes:
Owner:
Reviewer:
May work resume: Yes/No
Decision must be recorded in:
```

---

# 17. First protocol-governed pilot — LC-001

This task is proposed, not claimed, until Rox ratifies v0.2 and assigns it.

## 17.1 Pilot objective

Restore a green, internally consistent `main` and establish one trustworthy boundary before any new `v0.19.177` feature implementation.

## 17.2 Proposed assignment

- **Task Owner:** ChatGPT session
- **Independent Reviewer:** Claude session
- **Arbiter and merger:** Rox
- **Proposed branch:** `ai/chatgpt/LC-001-authority-webdoc-repair`
- **Proposed base:** exact current `main` head at claim time; record it before branching

ChatGPT is proposed as owner because the preceding ChatGPT working session is attributed with the prepare/generator/package sequence and therefore holds the most direct context. This is a per-task assignment, not a standing model identity. Claude reviews because it independently identified the mirror defect and has relevant gate/receipt expertise.

## 17.3 Task contract

```md
# TASK CONTRACT

Task ID: LC-001
Title: Authority, web-doc, and mirror reconciliation
Status: Proposed
Owner: ChatGPT session, subject to Rox ratification
Reviewer: Claude session
Requested by: Rox
Repository: derickonfire/linecheck-acceptance
Base commit: Record at claim time
Task branch: ai/chatgpt/LC-001-authority-webdoc-repair
Related boundary: v0.19.176+r3 acceptance / v0.19.177 preparation

Goal:
Produce a green exact-head result and one internally consistent release/roadmap/package state without adding new product behavior.

In scope:
- inspect run 31119008933 attempt 2 and retained artifacts;
- verify the accepted run/receipt claim for 50bc5a5 and determine its proper authority consequence;
- reconcile RELEASE-STATE.md, RELEASE-STATE.json, START-HERE, continuation, verification, and owner checklist where evidence requires;
- reconverge site/tools/build_web_doc.py and toolset/tools/build_web_doc.py under one documented source of truth;
- regenerate web-doc.zip and MANIFEST-SHA256.txt when required;
- run focused generator/package/mirror checks;
- regenerate the affected `MANIFEST-SHA256.txt` entries after reproducing and confirming the three receipt-binding mismatches;
- run the controlled gate and independently verify the exact-source receipt.

Out of scope:
- new v0.19.177 feature implementation;
- schema or migration changes;
- application behavior changes not strictly required by diagnosed evidence;
- Forge integration or marker redesign;
- production deployment or live data.

Acceptance criteria:
- release authorities agree on candidate/accepted status, completed Routine phase, next version, and exact evidence bindings;
- duplicated shared generators are byte-identical unless a new explicit architecture contract replaces mirroring;
- web-doc.zip is reproducible from the committed generator and authoritative state;
- manifest/package checks pass;
- controlled exact-head gate passes with zero hidden SKIPs;
- receipt verification succeeds against the same reviewed SHA;
- Claude independently reviews the diff and evidence;
- no direct push to main;
- Rox merges only the reviewed head.
```

## 17.4 Pilot sequence

1. Rox activates the no-direct-push rule or branch protection.
2. ChatGPT refreshes the repo and records the full declaration.
3. ChatGPT opens LC-001 from an exact base and reproduces the exact-source receipt-binding failure, including the three manifest hash mismatches.
4. ChatGPT verifies the earlier accepted r3 evidence rather than relying on a commit message.
5. ChatGPT proposes the smallest coherent authority and generator repair.
6. Focused checks prove mirror equality, package determinism, and truthful progress.
7. A draft pull request records the exact head and evidence.
8. Claude reviews the complete diff, reruns focused evidence, and independently verifies the receipt.
9. The controlled gate runs on the exact reviewed head.
10. Rox resolves any remaining authority contention and performs the merge.
11. Post-merge verification confirms green `main` and a synchronized release boundary.
12. Only then may the next contracted `v0.19.177` product task begin.

## 17.5 Pilot success criteria

The pilot succeeds only when ownership remained clear, no overlapping writes occurred, the authority contradiction was resolved without deleting evidence, the mirror invariant was restored, the exact receipt was independently verified, no gate was weakened, `main` finished green, and both models completed a milestone health check.

# 18. Forge independence and evaluation charter

## 18.1 Forge’s status

Forge is an experimental participant and possible continuity/evidence aid.

Forge is not:

- LineCheck’s owner;
- LineCheck’s release authority;
- a replacement for Git;
- a replacement for tests;
- a source of product requirements;
- permitted to override Rox, ChatGPT, Claude, GitHub Actions, or exact evidence.

## 18.2 Repository boundary

The Forge repository may read public or explicitly approved LineCheck inputs for a bounded evaluation. It may **never write to `linecheck-acceptance`**. Any future technical mechanism that would violate this rule requires a new protocol revision and Rox’s explicit decision; three-way model consensus alone is insufficient.

No task may add any of the following without explicit three-way approval from Rox, ChatGPT, and Claude:

- Git submodule or subtree;
- package dependency;
- copied Forge runtime;
- GitHub Action from Forge;
- cross-repository workflow;
- webhook;
- API call;
- MCP server;
- generated LineCheck state owned by Forge;
- Forge write access to LineCheck;
- LineCheck write access to Forge;
- release requirement that depends on the other repository.

## 18.3 Existing marker freeze

The current LineCheck gate’s Forge-named marker output is frozen as legacy behavior during the initial collaboration pilot.

The initial pilot should determine:

- whether the markers are merely a stable machine-readable receipt vocabulary;
- whether any external Forge runtime consumes them;
- whether the naming creates false confidence;
- whether the receipt can remain independently verifiable without Forge;
- whether the coupling should later be retained, renamed, isolated, or retired.

No decision should be hidden inside a release repair.

## 18.4 Per-use Forge evaluation

Every Forge use receives an entry:

```md
# FORGE EVALUATION

Evaluation ID:
Date:
LineCheck task:
LineCheck base/head:
Forge repository/version/commit:
Purpose:
Mode: Read-only advisory / Evidence parser / Other
Inputs provided:
Sensitive data provided: No
Output produced:
Claims made by Forge:
Claims independently verified:
Incorrect or unsupported claims:
Useful finding:
Finding that would likely have been missed without Forge:
Time/complexity added:
Workflow interruption:
Did Forge change the decision?:
ChatGPT helpfulness score: 0-5
ChatGPT verdict: Keep / Modify / Retire / Insufficient evidence
Claude helpfulness score: 0-5
Claude verdict: Keep / Modify / Retire / Insufficient evidence
Rox assessment:
Action for LineCheck:
Separate issue for Forge repository:
```

## 18.5 Forge value rules

Forge is helpful only when it measurably improves one or more of:

- continuity;
- exact-state recovery;
- evidence integrity;
- stale-document detection;
- handoff quality;
- reproducibility;
- reduced token/context burden;
- reduced owner intervention.

Forge is hindering when it:

- creates duplicate truth;
- asserts authority it does not have;
- expands context without improving decisions;
- adds brittle gates;
- creates false PASS confidence;
- obscures ordinary Git evidence;
- forces LineCheck to follow Forge’s roadmap;
- requires extensive maintenance unrelated to LineCheck’s product.

## 18.6 Cross-project feedback

When LineCheck reveals a Forge defect or improvement:

1. record it in LineCheck only as a bounded external observation;
2. open a separate Forge issue or planning entry;
3. implement and test it in `emotivus-forge`;
4. do not import that Forge change into LineCheck automatically;
5. require a new LineCheck integration decision if coupling is proposed.

---

# 19. GitHub governance recommendations

## 19.1 Highest-priority risk

The live API reported `main` as unprotected. This is the most urgent operational weakness in a two-AI workflow.

A strong acceptance system cannot prevent a direct push from bypassing review if the GitHub branch itself is unprotected.

## 19.2 Preferred protected-main policy

When the GitHub plan supports private-repository protection, configure `main` to require:

- pull request before merge;
- at least one human approval;
- required status check: the controlled runtime gate;
- branch up to date before merge for release-sensitive changes;
- dismissal of stale approvals when new commits arrive;
- resolution of review conversations;
- no force pushes;
- no branch deletion;
- restrictions applied to administrators where practical;
- signed commits only if the operational burden is acceptable;
- one chosen merge strategy, preferably squash for bounded tasks or merge commits if preserving task history is more important.

Do not enable a bypass for an AI account.

## 19.3 CODEOWNERS

Recommended initial file:

```text
# Rox remains the human owner of all project truth.
* @derickonfire

# Extra-sensitive areas.
/.github/ @derickonfire
/Release/ @derickonfire
/Planning/ @derickonfire
/site/tools/runtime-gate/ @derickonfire
/site/tools/run_all_checks.sh @derickonfire
/site/app/schema.php @derickonfire
/MANIFEST-SHA256.txt @derickonfire
/web-doc.zip @derickonfire
```

AI models should not be represented as CODEOWNERS unless they operate through distinct, accountable GitHub identities and Rox deliberately chooses that policy. A human approval must remain decisive.

Protect the CODEOWNERS file itself.

## 19.4 Private repository without GitHub Pro

GitHub’s official documentation indicates private-repository protected branches/rulesets require an eligible paid GitHub plan.

When protection is unavailable:

- establish a written no-direct-push rule;
- use draft PRs for every task;
- let Rox perform all merges;
- verify exact head SHA immediately before merge;
- never merge from a model’s summary alone;
- use the controlled workflow on every PR and push;
- record reviewer outcome in the PR;
- retain receipts before release activation;
- periodically inspect branch history for direct pushes;
- consider upgrading GitHub rather than making a private codebase public for governance features.

Manual policy is weaker than enforced policy. Treat the plan upgrade as a risk-reduction decision, not a convenience feature.

## 19.5 Pull request template

```md
## Task contract

Task ID:
Owner:
Reviewer:
Base SHA:
Head SHA:
Related release/phase:

## Goal

## Scope

## Files changed

## Behavior changed

## Evidence

Commands:
Results:
SKIPs:

## Risk review

- [ ] No secrets or production data
- [ ] No unapproved schema/migration change
- [ ] No gate weakening
- [ ] No unrelated refactor
- [ ] Release/docs synchronized where required
- [ ] Forge boundary respected

## Review

Reviewer outcome:
Unresolved threads:
Rox decision:
```

---

# 20. Security, privacy, and destructive-action rules

Neither model may, without explicit Rox authorization:

- connect to the production database;
- run data repair against live staff records;
- expose credentials;
- add secrets to a prompt, issue, log, artifact, or repository;
- deploy to production;
- change DNS or hosting;
- delete Git history;
- force-push;
- delete release evidence;
- rewrite an accepted receipt;
- create fabricated audit events;
- mark historical work reviewed when it was not;
- run untrusted repository hooks with broad permissions;
- use Claude’s `--dangerously-skip-permissions`;
- grant Forge cross-repository write access.

Use disposable databases and bounded sandboxes.

Review repository-local AI configuration before trusting it. Instruction files are guidance; hooks and permissions can execute or constrain actions and deserve code review.

---

# 21. Collaboration health check

Complete after every milestone and after any serious contention. Do not require a full health-check file for every small task; record one consolidated check at the milestone boundary.

```md
# COLLABORATION HEALTH CHECK

Milestone:
Date:
Tasks completed:
ChatGPT roles:
Claude roles:
Owner interventions:

## Delivery
Did task ownership remain clear?:
Were branches/worktrees isolated?:
Did either model exceed scope?:
Did the handoffs contain enough evidence?:
Did independent review find material issues?:
Were CI and controlled evidence reproducible?:

## Quality
Defects found before merge:
Defects found after merge:
Gate failures caused by implementation:
Gate failures caused by environment:
Documentation contradictions:
Stale-context incidents:
Merge conflicts:
Rework commits:

## Role fit
Where ChatGPT added the most value:
Where Claude added the most value:
Task that should transfer next time:
Recommended role change:

## Forge
Forge used:
Helpful findings:
Incorrect claims:
Extra burden:
ChatGPT verdict:
Claude verdict:
Rox verdict:

## Decision
Keep protocol unchanged / Modify / Pause parallel work
Required protocol changes:
```

## 21.1 Metrics to track

Use trends, not one-task conclusions:

- first-pass acceptance rate;
- number of review blockers;
- post-merge defect count;
- overlap incidents;
- merge conflict count;
- stale-base incidents;
- average number of revisions;
- owner escalations;
- evidence completeness;
- task cycle time;
- Forge helpfulness and false-claim rate;
- percentage of tasks completed without roadmap or release drift.

---

# 22. Implementation roadmap

Each slice ends in a clean commit or recorded decision. Governance setup and product work remain separate.

## Phase 0 — Ratify the live boundary and stop direct pushes

### Slice 0A — Rox ratification

- review this v0.2 reconciliation;
- approve, amend, or reject the LC-001 assignment;
- confirm no new v0.19.177 product work begins before LC-001;
- confirm no production or live-database work is authorized.

### Slice 0B — Enforcement first

- enable protected-main rules when available; or
- record and begin the §19.4 manual regime immediately;
- require draft pull requests and Rox-controlled merges.

**Exit:** no-direct-push rule is active and LC-001 may be claimed.

## Phase 1 — LC-001 authority and web-doc repair

- reproduce the current exact-head failure;
- reconcile accepted evidence with all release authorities;
- restore generator mirror equality;
- regenerate and verify package/manifest outputs;
- obtain a green exact-head gate and independently verified receipt;
- merge through a reviewed pull request;
- complete a milestone health check.

**Exit:** green, internally consistent `main` with one truthful roadmap boundary.

## Phase 2 — Minimal collaboration scaffolding

### Slice 2A — Shared instructions

Add `AGENTS.md`, `CLAUDE.md`, `REVIEW.md`, and `Planning/AI-COLLABORATION/README.md` in a governance-only pull request.

### Slice 2B — Active coordination

Add `TASK-BOARD.md`, `DECISIONS.md`, and `HANDOFFS/README.md` only with concise operational content.

### Slice 2C — Pull-request governance

Add the pull-request template and CODEOWNERS. Document the enforced or manual merge boundary.

**Exit:** minimal collaboration layer merged without product behavior changes.

## Phase 3 — First v0.19.177 implementation task

- create one bounded product task from the reconciled authority;
- assign owner/reviewer per task evidence;
- use exact base, isolated branch, full handoff, independent review, and gate;
- do not parallelize a second feature yet.

## Phase 4 — Controlled parallel pilot

Choose two low-coupling tasks with distinct write scopes, branches, and common base. Cross-review after both are ready.

**Exit:** zero overlapping writes, no stale-base incident, and no authority drift.

## Phase 5 — Adaptive specialization

Compare first-pass acceptance, review blockers, rework, scope violations, owner intervention, and evidence quality. Revise role defaults from results.

## Phase 6 — Read-only Forge trial

Only after LineCheck collaboration is stable, select one continuity/evidence task, expose no secrets, record the exact Forge version and inputs, require both models to verify outputs, and create `FORGE-EVALUATION.md` with an explicit Keep/Modify/Retire/Insufficient Evidence decision.

## Phase 7 — Mature workflow

Only after successful pilots may the project expand parallelism, automate stale-base or task-contract checks, consider path-based rules or separate AI identities, or evaluate narrow interoperability. Rox remains final arbiter.

# 23. Ready-to-paste shared kickoff prompt

Paste this into both sessions after providing v0.2:

```text
You are participating in the LineCheck Dual-AI Collaboration Protocol v0.2.

LineCheck authority is the live derickonfire/linecheck-acceptance repository. Refresh it before relying on this prompt. Record observed_at, origin/main, the controlling CI run, and all authority contradictions.

The dated v0.2 snapshot observed main at bcbf9a9a075366a14a5a5fcdb443cd03ae97becf with a completed failing exact-head gate, contradictory RELEASE-STATE.md and RELEASE-STATE.json, and divergent site/toolset build_web_doc.py mirrors. Treat those facts as stale until rechecked, but do not silently dismiss them.

No new v0.19.177 product implementation begins before Rox authorizes and LC-001 establishes a green, internally consistent baseline.

Every implementation task has one owner, one independent reviewer, an exact base SHA, a distinct branch/worktree, declared write scope, acceptance criteria, and complete handoff. Never push directly to main. Never weaken a gate to obtain PASS. A SKIP is not a PASS. Preserve shared-tool mirror invariants.

Default strengths are tie-breakers only. Roles are assigned per task and may transfer through the protocol. Forge is separate, advisory, and read-only toward LineCheck.

Do not claim background monitoring or scheduled follow-up unless a visible Rox-authorized automation actually exists.

Return:
1. Full or short Session Declaration, as appropriate.
2. Current authoritative state and exact CI verdict.
3. Contradictions or stale facts.
4. Proposed owner/reviewer for the exact next action.
5. Whether work may safely begin.
Do not edit until the task is authorized and claimed.
```

# 24. ChatGPT-specific startup prompt

```text
Act as the proposed ChatGPT Task Owner for LC-001 under LineCheck Dual-AI Collaboration Protocol v0.2. Ownership is not active until Rox ratifies it.

Refresh the live repository and CI. Do not assume the dated protocol snapshot still applies. Reconcile, rather than overwrite, the evidence that v0.19.176+r3 passed on 50bc5a5 with the contradictory current release authorities and the current exact-head receipt-binding failure.

Your emphasis for LC-001 is release/document coherence, generator/package behavior, mirror reconvergence, source-manifest repair, scoped implementation, and an evidence-complete handoff. Diagnose before editing. Reproduce the three exact-source mismatches before changing them. Treat site/tools/build_web_doc.py and toolset/tools/build_web_doc.py as one high-contention mirror pair. Do not begin new v0.19.177 product behavior.

Use branch ai/chatgpt/LC-001-authority-webdoc-repair only after recording the exact current base. Open a draft PR. Never push directly to main. Do not alter expected counts, SKIP semantics, receipt binding, or gate behavior merely to make CI green.

Return the full Session Declaration, reproduced failure, proposed bounded task contract changes, and whether the task may safely start.
```

# 25. Claude-specific startup prompt

```text
Act as the proposed Independent Reviewer for LC-001 under LineCheck Dual-AI Collaboration Protocol v0.2. The assignment is not active until Rox ratifies it.

Refresh the live repository and CI. Verify all statements in your earlier response against the current exact head, including the accepted r3 run, current failure, release-state contradiction, and mirror divergence. A completed exact-head verdict supersedes an earlier pending or outage narrative.

Do not edit the owner’s branch. Review the exact task contract and diff. Independently verify the accepted evidence, generator mirror equality, package reproducibility, release-authority consistency, gate integrity, and exact-source receipt. Do not use --dangerously-skip-permissions.

Roles are per task. Forge remains separate, advisory, and unable to write LineCheck.

Return the full Session Declaration, current contradictions, reviewer plan, and whether LC-001 may safely begin.
```

# 26. Reviewer prompt

```text
Review this LineCheck task under the Dual-AI Collaboration Protocol.

Do not begin from the author’s summary. Begin from the task contract, base SHA, head SHA, live release authority, and exact diff.

Independently evaluate:
- scope compliance;
- behavior and negative paths;
- authorization, privacy, and data safety;
- schema/migration consequences;
- UI/accessibility consequences;
- documentation and release truth;
- whether tests genuinely executed;
- all SKIPs;
- changes to expectations, fixtures, retries, and gate logic;
- exact-source receipt binding;
- shared-tool mirror byte-identity under Rule 15, unless an approved divergence is explicitly documented;
- Forge boundary compliance.

Run the required evidence independently where the environment permits. State every item you could not reproduce.

Return one formal outcome:
APPROVE
APPROVE WITH NON-BLOCKING FOLLOW-UPS
REQUEST CHANGES
BLOCK — AUTHORITY CONFLICT
BLOCK — EVIDENCE INCOMPLETE
ESCALATE TO ROX
```

---

# 27. Cross-model consensus prompt

Use after both models have reviewed the same decision:

```text
Produce a consensus record without erasing disagreement.

List:
1. facts both models agree on;
2. ChatGPT’s position;
3. Claude’s position;
4. evidence supporting each position;
5. unresolved assumptions;
6. risk of each option;
7. recommended option;
8. whether the recommendation is unanimous;
9. the exact decision Rox must make;
10. what work is frozen until that decision.

Do not describe silence as agreement. Do not average incompatible technical claims. Preserve dissent.
```

---

# 28. First owner decision checklist

Before repository implementation begins, Rox should decide:

- [ ] Ratify protocol v0.2 as the working collaboration constitution.
- [ ] Confirm `derickonfire/linecheck-acceptance` is the only LineCheck authority.
- [ ] Confirm `derickonfire/emotivus-forge` remains separate and read-only toward LineCheck.
- [ ] Activate branch protection or the manual no-direct-push regime immediately.
- [ ] Freeze new `v0.19.177` product implementation until LC-001 is accepted.
- [ ] Approve LC-001 as the first pilot.
- [ ] Confirm ChatGPT as proposed Task Owner and Claude as Independent Reviewer for LC-001, or record a different per-task assignment.
- [ ] Confirm the existing Forge marker behavior remains frozen.
- [ ] Confirm no production deployment, live database, or destructive work is authorized.
- [ ] Require a milestone health check after LC-001.
- [ ] Approve minimal collaboration scaffolding only after the baseline repair, unless enforcement requires CODEOWNERS or the PR template sooner.

---

# Appendix A — Reconciliation of Claude’s response

Claude returned **ACCEPT WITH CONDITIONS** and accepted the builder–reviewer architecture, one owner/one reviewer discipline, GitHub coordination, exact SHAs, evidence over narrative, adaptive specialization, Forge separation, and Rox as arbiter.

## Accepted directly

- per-task roles, with defaults only as tie-breakers;
- mirror invariant for duplicated tools;
- proportional session ceremony;
- branch protection or manual no-direct-push enforcement before process niceties;
- refreshed kickoff prompts;
- deferral of empty health/Forge records;
- explicit run-and-receipt acceptance evidence;
- a real web-doc repair as the first pilot;
- Forge read-only posture toward LineCheck.

## Accepted with refinement

- **Live state:** Claude’s initial response was correct that r3 has a successful exact-source run and that the post-r3 commit sequence was not mysterious. Its statement that the head rerun was still pending expired before v0.2 was prepared. Claude’s final review then supplied the retained attempt-2 log proving that all 80 acceptance groups passed and exact-source receipt verification failed on three stale manifest hashes.
- **Acceptance classification:** Claude described r3 as accepted and promoted. v0.2 preserves the successful evidence but does not declare the repository globally reconciled because the live Markdown and JSON authorities currently contradict one another.
- **Pilot scope:** LC-001 includes Claude’s web-doc and mirror repair, expanded to reconcile release authority and the exact-head receipt-binding failure.
- **Determinism bar:** v0.2 requires dozens of consecutive passes and uses 50/50 when risk or observed intermittency justifies it, rather than imposing exactly 50 on every harness change.
- **Commit attribution:** Claude attributes the prepare/generator/package sequence to the prior ChatGPT working session. That supports ChatGPT ownership for continuity, but task ownership still requires Rox’s explicit ratification.

## Additional safeguards added by ChatGPT

- observed-at timestamps and snapshot expiry;
- completed exact-head verdict precedence;
- separation of empirical acceptance evidence from synchronized repository authority;
- prohibition on fabricated background monitoring, while permitting real disclosed and cancellable automations;
- explicit freeze on new v0.19.177 feature implementation until LC-001 produces a green, truthful baseline.


---

# 29. Consensus and activation state

## 29.1 Two-model consensus

**CONSENSUS DECLARED — v0.2 final (with §2.2 correction applied).**

ChatGPT accepts Claude’s blocking correction to the run `31119008933` attempt-2 narrative and adopts both non-blocking refinements:

1. Rule 17 permits only real, disclosed, cancellable automations or scheduled tasks and prohibits fabricated monitoring claims.
2. Reviewer responsibilities and the reusable reviewer prompt explicitly require verification of Rule 15 mirror byte-identity or an approved documented divergence.

Claude’s written review states that this correction converts its outcome from `REQUEST CHANGES` to `APPROVE` and declares consensus. No substantive model-to-model disagreement remains.

## 29.2 What consensus does and does not authorize

Two-model consensus finalizes the protocol text. It does **not** independently authorize repository mutation, direct pushes, merge, deployment, or new `v0.19.177` product work.

Work begins only after Rox:

1. ratifies this final protocol;
2. declares the §19.4 manual no-direct-push regime active, unless equivalent branch protection is already enforced;
3. authorizes LC-001 with ChatGPT as Task Owner and Claude as Independent Reviewer.

## 29.3 Kickoff order

1. Rox sends the §24 starting prompt to ChatGPT first.
2. ChatGPT refreshes the repository, claims LC-001 from an exact base, creates the governed branch, reproduces the receipt-binding failure, implements the bounded repair, opens a draft pull request, and produces the handoff packet.
3. Only after the draft PR and handoff exist, Rox sends Claude the §25 starting prompt together with the PR number, branch, exact head SHA, and handoff packet.
4. Claude performs independent review and returns one formal §15.2 outcome.
5. Rox merges only the reviewed exact head after the required gate and receipt verification are green.

---

# 30. Research basis

The protocol deliberately uses ordinary software-engineering controls rather than assuming an AI-specific orchestration framework is trustworthy.

## 30.1 Git worktrees

Git officially supports multiple working trees attached to one repository, allowing more than one branch to be checked out at the same time while each worktree has its own working state.

Source:  
https://git-scm.com/docs/git-worktree

## 30.2 GitHub review and branch controls

GitHub documents:

- CODEOWNERS for assigning responsible owners;
- protected branches and rulesets for requiring pull requests and status checks;
- blocking force pushes;
- requiring code-owner review;
- protecting the CODEOWNERS file itself.

Sources:

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets

## 30.3 OpenAI repository instructions

OpenAI documents `AGENTS.md` as a way to tell Codex how to navigate a repository, which commands to run, and which project practices to follow. OpenAI also emphasizes isolated task environments, verifiable logs/test outputs, and manual review before integration.

Source:  
https://openai.com/index/introducing-codex/

## 30.4 Claude project instructions

Claude Code documents `CLAUDE.md` as persistent project context loaded at session start. Anthropic recommends using it for conventions, architecture, commands, and review checklists, while using permissions or hooks for boundaries that must be enforced.

Sources:

- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/overview
- https://code.claude.com/docs/en/debug-your-config
- https://www.anthropic.com/engineering/claude-code-best-practices

## 30.5 Multi-agent software-engineering research

Research supports the potential value of role specialization and cross-team exchange, but also identifies orchestration, trustworthiness, human-agent coordination, and evaluation as open challenges. This protocol therefore treats specialization as a measured hypothesis and keeps a human arbiter.

Sources:

- Junda He, Christoph Treude, and David Lo, *LLM-Based Multi-Agent Systems for Software Engineering: Literature Review, Vision and the Road Ahead*  
  https://arxiv.org/abs/2404.04834
- Zhuoyun Du et al., *Multi-Agent Software Development through Cross-Team Collaboration*  
  https://arxiv.org/abs/2406.08979
- Yongjian Tang and Thomas Runkler, *LLM-Based Agentic Systems for Software Engineering: Challenges and Opportunities*  
  https://arxiv.org/abs/2601.09822

---

# 31. Final operating principle

The models are collaborators, not authorities.

The repository is the shared record.  
The task contract defines ownership.  
The branch isolates work.  
The reviewer challenges the result.  
The gate produces evidence.  
Forge is evaluated, not trusted by default.  
Rox decides when intelligent systems disagree.

**Optimize for LineCheck, not for ChatGPT, Claude, or Forge.**
