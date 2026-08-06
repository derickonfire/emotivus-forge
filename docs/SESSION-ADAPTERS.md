# Optional Five-Command Session Adapters

A host — an MCP server, a coding-agent hook, a CI step — may ask Forge what it should invoke at a session lifecycle event. Forge answers with a declarative contract. It does not install itself, watch anything, or run in the background.

## Events

| Event | Behavior | Mode |
|---|---|---|
| `session_start` | Run Forge, the bounded active pass | invoke |
| `milestone` | Check | invoke |
| `session_end` | Session Close | **guide only** |

`session_end` is guidance. It never performs the close, and setting it to `invoke` is rejected.

## Off by default

The shipped configuration disables everything:

```json
"session_adapters": {
  "enabled": false,
  "events": {
    "session_start": {"enabled": false},
    "milestone": {"enabled": false},
    "session_end": {"enabled": false}
  }
}
```

The global switch dominates. With `enabled` false, every per-event switch resolves inactive, so enabling one event by accident cannot activate the layer. An invalid configuration also resolves inactive — a rejected config never partially applies.

## Prohibitions enforced in code

These are validated, not merely documented. A configuration requesting any of them is **rejected**, not quietly ignored:

`advance_baseline`, `approve_changes`, `merge_files`, `authorize_release`, `adopt`, `ship`, `mutate_state`, `rewrite_prompt`, `run_continuously`

Additionally:

- **No sixth public command.** Only Help, Adopt, Resume, Check, and Ship may be mapped.
- **No ninth state file.** Adapters read settings and emit a contract; they persist nothing.
- **No daemon.** The contract declares `process_model: host-invoked-one-shot` and `runs_continuously: false`.
- **No hook installation or prompt rewriting.** Both are declared false in the contract.

## Authority

An invocation through an adapter carries exactly the authority of the same command run by hand — no more. Observed state is still not owner-authorized state. A Check invoked by a milestone hook authorizes nothing.

## Settings schema

Adapters arrive in **settings schema 21**. Projects on schema 20 migrate automatically and receive the block with everything off. Core state schema remains 4 and the top-level state file count remains eight.
