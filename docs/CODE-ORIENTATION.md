# Non-Authoritative Code Orientation

Orientation answers "where does work happen in this project" so a session spends its
attention well. It is **inference**, and it is marked as inference everywhere.

## Three views

| View | Source | Meaning |
|---|---|---|
| `active_zones` | Change ledger only | Directories weighted by recorded change events. |
| `centrality` | Shallow text references | Files weighted by how many *other* files mention their stem. |
| `coupling` | Change ledger only | File pairs recorded changing together at least twice. |

## What orientation may never do

Every record carries `authority: "none"` and `evidence_tier: "inferred"`, and the result
declares four explicit refusals:

    advances_baseline: false
    qualifies_check: false
    authorizes_release: false
    becomes_governed_fact: false

A file that scores high is a file worth **looking at**, never a file proven important.

## Deliberate limits

- **No filesystem timestamps.** Mtimes vary by checkout, copy, and archive extraction, so
  they cannot distinguish real activity from a fresh clone. A regression asserts the module
  never reads `st_mtime`, `getmtime`, `st_ctime`, or `st_atime`.
- **No ledger means unknown, not zero.** Absent history produces an explicit knowledge gap.
  Reporting "no active zones" for a project Forge simply cannot see would be a false claim.
- **Ambiguous stems are flagged.** Two files named `utils.py` cannot both be credited for a
  bare `utils` reference, so both are marked `ambiguous_stem`.
- **Sweeping events are skipped.** An event touching more than sixty paths couples everything
  with everything; it is excluded and counted in `wide_events_skipped`.
- **Self-references never count.** A file mentioning its own name proves nothing.
- **Nothing is persisted.** Orientation writes no file and adds no ninth state file, no sixth
  public command, and no daemon.

## Truth boundary

Orientation is not a call graph, not dependency resolution, and not proof that any file
matters. It uses whole-word stem matching, which is shallow by design: it needs no language
server, no parse tree, and no network, and it degrades honestly across mixed-language trees.
A high score means look here first. It never means authorized, verified, or important.
