# State Integrity and Transactions

Forge treats `.forge/` as project continuity evidence, not disposable cache.

## Corruption behavior

Malformed JSON state blocks the operation. Forge preserves the exact damaged file and never substitutes an empty object. JSONL readers recover valid object records line by line for diagnosis, report malformed line numbers, and block further writes until the state is explicitly repaired or restored.

## Schemas

`settings.json` and `state.json` currently use schema 2. Schema-1 documents migrate through explicit one-step migration functions. Unsupported future schemas block rather than being guessed backward.

## Operation boundary

Mutating public commands acquire one project lock. The eight top-level state files are snapshotted before the operation and restored if the command fails or is interrupted by an exception. The temporary lock file is removed after the operation and does not become a ninth state file.

Native evidence produced by an external project process is not rolled back automatically; it may remain as orphaned raw evidence after an interrupted command and must not be treated as current until reconnected by a successful Forge record.

## Durable writes

JSON, Resume text, and JSONL writes flush and synchronize before Forge reports success. JSON documents use atomic replacement.

## Ledger chain

New Ledger events include `previous_event_hash` and `event_hash`. Forge verifies content hashes and linkage before writing. This detects modification or deletion within the locally available chain; it is not a signature, remote timestamp, or third-party attestation.
