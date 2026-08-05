# Forge Execution Control

Forge must never convert a killed or timed-out process into a green result.

## Self-test isolation

Forge self-tests run as isolated shards rather than one monolithic process. The current Python regression suite keeps small `unittest.TestCase` classes intact and automatically divides larger classes into bounded method chunks. Each shard has:

- an independent Forge-owned shard-runner subprocess and process group;
- an explicit timeout;
- immediate checkpointing;
- a retained result and output;
- resumability only when the Forge source fingerprint is unchanged.

Use a bounded execution window when the surrounding agent or host has a hard limit:

```bash
python3 forge.py self-test --fresh --budget-seconds 30
python3 forge.py self-test --resume --budget-seconds 30
```

A budget boundary returns `INCOMPLETE`, records `halt_reason: overall-budget`, and supplies a resume command. It is not a failure and never counts as a pass.

A shard that exceeds its own declared timeout returns `TIMEOUT` and blocks certification.

## Single-run ownership and external termination

Only one Forge self-test may own a workspace at a time. An atomic, process-owned run directory in the operating-system temporary runtime area—keyed to the project path and outside project ZIP cleanup—rejects concurrent certification immediately instead of allowing two runs to overwrite progress, mutate the same test authority, or compete for resources. Stale ownership is reclaimed only after the recorded process is no longer alive. Filtered diagnostic runs use separate progress files and cannot replace full-suite evidence.

Forge installs bounded SIGTERM and SIGINT cleanup while certification is active. The ownership record and active subprocess are process-scoped rather than inferred from a lingering output file. If the surrounding AI host, shell, or operating system stops Forge, Forge terminates its active shard process group and releases the run lock before exiting. An external kill is never converted into `PASS`; the existing checkpoint remains the latest valid evidence and the next invocation resumes from it when the source fingerprint is unchanged.

The host timeout should still be longer than `--budget-seconds` so Forge can pause itself cleanly. Signal cleanup is the last-resort safety boundary, not a substitute for an honest internal budget.

## Project checks

External project commands already run in isolated process groups with explicit command timeouts and checkpoint after every completed check. Release claims remain unsupported while any required check is `NOT_RUN`, `ERROR`, `FAIL`, or timed out.

Internal Forge stages are being moved behind the same isolated execution envelope during the 1.4.x hardening cycle. Until that work is complete, large internal discovery or proof stages must be run in bounded profiles and their incomplete state preserved honestly.

## Status meanings

- `PASS`: every required shard or check completed and passed.
- `FAIL`: a required assertion, command, or evidence contract failed.
- `TIMEOUT`: an individual stage exceeded its declared limit.
- `INCOMPLETE`: execution paused before all required work completed.
- `NOT_RUN`: no evidence exists for that required stage.

Only `PASS` supports the associated claim.

## Detached descendant output safety

A timed-out shard may have launched descendants that detach into another process group while inheriting the shard's output stream. Forge captures shard output in a bounded temporary file rather than an inherited pipe, terminates the owned process group, checkpoints `TIMEOUT` or `INCOMPLETE`, and returns control without waiting for detached descendants to close output handles.

Forge also reserves cleanup time and will not start another shard when less than five usable seconds remain in the declared wall-clock budget.
