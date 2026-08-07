# G3 · Cross-Model Evolution Kernel — foundation certification

**Verdict: FOUNDATION CERTIFIED → CONTINUOUS (as of 0.572).** Every clause of the G3
completion rule is delivered and adversarially tested, and the full round trip passes
end to end. Per the goal's own terms, G3's foundation is complete and G3 now remains
**continuous by design** (each new instrument requires an observed miss + scored trial).

## Completion rule

> The foundation is complete when another model/vendor can migrate an older package,
> preserve exact meaning, replace an obsolete component, and emit a compatible
> continuity package.

## Clause → evidence

| Clause | Delivered | Evidence |
|---|---|---|
| **Migrate an older package** | Forward-compatible migration preserves unknown top-level and nested fields verbatim (0.567) | `core/forward_compat.py`; `test_forward_compat` |
| **Preserve exact meaning** | Unknown fields carried verbatim and *reported* as preserved-but-unrecognized; a full round trip preserves them into the consuming instance | `test_forward_compat`, `test_g3_roundtrip::test_g3_completion_round_trip` |
| **Replace an obsolete component** | Explicit lifecycle records (retain/fold/freeze/retire/replace, 0.569), instance-bound so imported forgeries are labeled self-consistent (0.570), with **verified** invariants checked against scoped-Check truth (0.571) | `test_lifecycle_transition` (record, binding, invariant verification) |
| **Emit a compatible continuity package** | Vendor-neutral continuity kernel (0.568) + continuity-bundle export/import restoring the eight state files into a fresh instance | `test_run_forge_experience` (vendor-neutral), `test_native_invocation_handoff` (bundle import), `test_g3_roundtrip` |
| **Cross-model trust (supporting)** | Instance-binding: an imported package's authority/provenance/lifecycle is self-consistent, never authentic, unless a shared collaboration secret is enrolled (0.562–0.564, 0.570) | `test_authority_baseline`, `test_provenance_delivery`, `test_lifecycle_transition` |

## End-to-end round trip (P4-06)

`test_g3_roundtrip::test_g3_completion_round_trip` walks the whole rule with real Forge
calls: a source project carrying an unrecognized field is migrated (field preserved),
an obsolete component is **replaced** with a declared invariant that Forge **verifies**
as PRESERVED, a session is closed and a continuity bundle exported, and a **fresh target
instance imports it** — restoring all eight state files, the preserved unknown field, and
the recorded replacement (successor intact). Exact meaning survives the round trip.

## Adversarial validation (P4-08)

A 12-agent adversarial field test at 0.569 attacked the G3 surfaces and found two genuine
over-assertions of Forge's own ethos — lifecycle transitions were unsigned, and the
vendor-neutral filter screened only keys. Both were closed and regression-locked in 0.570
(`planning/G3-FIELD-TEST-OBSERVED-MISSES.md`). Ten of twelve lenses held or were refuted.

## Honest boundaries (what "foundation certified" does and does not claim)

- Forge preserves and reports unrecognized fields; it does **not** interpret or trust them.
- Invariant verification confirms declared, Forge-observable invariants still hold; it does
  **not** prove the successor is correct or complete.
- Cross-model trust is between owner-provisioned parties (symmetric collaboration secret);
  an unenrolled imported package is always self-consistent, never authentic.
- `release_authorization` remains **false** — certification is of the evolution *foundation*,
  not of any specific release.

## Disposition

G3 moves from **FOUNDATION_ACTIVE** to **CONTINUOUS**. G1 is COMPLETE (0.566); G3's
foundation is certified (0.572); **G2 (one-command session continuity) is the remaining
open goal.**
