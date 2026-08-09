# LineCheck Central AI Communication Authority v1

**Owner directive:** General instructed Codex to build and implement the missing central communication procedure on 2026-08-09.
**Effective:** immediately for LineCheck cross-agent coordination.
**Incorporated authority:** LineCheck AI Operating Agreement v0.3 section 5, GitHub and Forge Communication Contract, Monitoring Contract, and task-specific Active Work Register assignments.
**Product effect:** none. This changes communication control only; it authorizes no product, runtime, schema, migration, release, archive, gate, PR-closure, merge, or product-main action.
**Future documentation work:** the next authorized governance-document amendment must incorporate this procedure into the merged LineCheck planning files without silently rewriting historical records.

## 1. Why this exists

GitHub remains operational code, exact-head, review, and CI truth. Forge remains the durable append-only coordination ledger. Those channels existed, but neither provided one canonical actionable inbox. Agents could therefore narrate “waiting,” monitor only the wrong surface, or require General to relay a message even though a durable receipt existed elsewhere.

This procedure adds one central communication authority without creating a conflict-prone shared mutable file.

## 2. Authority hierarchy

For communication state, use this order:

1. General’s explicit current directive is final owner authority.
2. GitHub exact head, checks, reviews, comments, and merge state are operational product and gate truth.
3. Forge exchange/attention is the central cross-agent action and acknowledgement authority.
4. Forge exchange/threads is the durable detailed proposal, review, evidence, correction, and decision ledger.
5. LineCheck’s merged AI Operating Agreement, Communication Contract, Monitoring Contract, Active Work Register, and Controlled Multi-Agent Execution Protocol govern roles and procedure.
6. Conversation status boards, remembered context, and agent prose are advisory only. They never prove action, monitoring, workers, CI, review, or receipt.

Where an exact GitHub fact conflicts with a Forge or chat claim, GitHub controls the product/gate fact. Where an agent says it is waiting but no valid unacknowledged attention event exists, the waiting claim is invalid.

## 3. Central attention authority

Canonical path:

exchange/attention/<author-lane>/NNNN-<slug>.json

Rules:

- The lane name is the author, not the recipient. Each author writes only its own lane.
- One event is one new immutable JSON file.
- Sequence numbers are zero-padded and strictly increasing within the author lane.
- Never edit or delete a published attention event. Corrections are later events referencing supersedes.
- Git commit time is receipt time.
- Detailed material remains in exchange/threads; the attention event points to it.
- A response may be a matching attention acknowledgement plus a detailed thread return, or a detailed thread return that explicitly binds the attention event ID.
- No shared mutable state file is permitted. Current action state is derived from append-only events and acknowledgements.

## 4. Required event schema

Every action-required event contains:

- schema_version
- id
- from
- to
- human_title
- technical_thread
- event_type
- source_message
- source_commit
- exact_product_repo
- exact_product_head when applicable
- gate_state when applicable
- required_action
- expected_response
- expected_response_lane
- prohibited_actions
- created_utc
- supersedes when applicable

Allowed event types:

- ACTION_REQUIRED
- REVIEW_REQUIRED
- ACK_REQUIRED
- DECISION_REQUIRED
- CORRECTION
- ACKNOWLEDGEMENT
- CLOSED

A valid acknowledgement contains:

- its own immutable event ID;
- in_reply_to with the exact attention event ID;
- the source message and commit received;
- the exact product head and review ID when applicable;
- the resulting state;
- any remaining holds.

## 5. No-waiting rule

An agent may say WAITING only when all are true:

1. A valid attention event addresses the other agent.
2. The event points to an existing immutable thread message and commit.
3. No later acknowledgement or substantive return closes it.
4. The expected response window has not been superseded by a newer owner instruction.

If those conditions are not met, the agent must either create the missing attention event, inspect the relevant authority, or state UNVERIFIED. General must never relay ordinary cross-agent messages.

## 6. Monitor procedure

Every LineCheck communication monitor performs this order:

1. Read exchange/attention for new events addressed to the monitored agent.
2. Match each event to acknowledgements or substantive returns by exact event ID.
3. Read referenced Forge thread messages and verify their Git commits.
4. Query GitHub for any referenced exact head, CI, review, comment, and merge fact.
5. Correct stale status boards immediately.
6. Route bounded non-owner gaps directly through a new attention event.
7. Notify General only for:
   - a decision that only General may make;
   - a genuine unresolved blocker after the procedure was followed;
   - automation or authority failure;
   - a newly decision-ready package.

The live Codex heartbeat configuration is operational monitoring truth. Static cadence prose is not.

## 7. Proof of work and agent honesty

No agent may claim:

- workers were launched without actual worker IDs;
- workers are active without a reachable-agent result;
- review exists without an exact GitHub review or Forge message identity;
- CI passed without the exact workflow/check receipt;
- a file or packet exists without an exact repository path and commit;
- continuous monitoring without a disclosed automation;
- waiting without a valid unacknowledged attention event.

Session-scoped workers are not visible across unrelated sessions. An agent never infers workers from remembered conversation context.

## 8. Task and title discipline

Every event and every first paragraph mentioning a technical identifier must also state the human title. Technical IDs may be abbreviated later in the same bounded communication.

Each task has exactly one Task Owner, one Independent Reviewer, and General as sole arbiter/merger. Task-specific Active Work Register assignments override generic roster examples.

## 9. Current adoption

Effective immediately:

- Codex’s LineCheck heartbeat reads exchange/attention before ordinary thread discovery.
- Codex and Claude use exchange/attention for action, review, acknowledgement, correction, and owner-decision routing.
- Existing thread messages remain valid and immutable.
- Current unacknowledged actions are backfilled with a new attention event rather than editing old thread messages.
- This procedure will be incorporated into the product governance documents through the next separately authorized documentation amendment.

## 10. Safety boundary

This communication authority cannot:

- merge or mark a PR ready;
- modify LineCheck product code or product documentation;
- change schema or run migrations;
- archive, move, delete, or close historical material;
- weaken, wire, retire, or relabel a gate;
- begin Packet C;
- make a product or authority decision reserved to General.

It coordinates authorized work; it never expands authorization.

General remains final arbiter and sole merger.
