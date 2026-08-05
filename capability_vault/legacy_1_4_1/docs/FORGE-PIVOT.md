# Forge Pivot

Forge Pivot is the controlled-change workflow inside the **Change** core. It exists so a project can replace a framework, language, game engine, architecture, database, major subsystem, or product direction without preserving obsolete implementation or losing enduring obligations.

Pivot is not a prohibition system. Risk is guidance. The release boundary remains strict, while exploration remains deliberately flexible.

## The lifecycle

1. **Create** — state the new direction, affected paths, expected breakage, obligations, quality targets, standards, migrations, tests, and release evidence.
2. **Assess** — use Graph and Impact to identify affected code, learned contracts, Ledger records, standards, tests, and live checks.
3. **Classify** — decide what to retain, revise, suspend, replace, retire, restore, or supersede.
4. **Activate** — preserve a last-green assurance checkpoint and create a linked transition Plan.
5. **Move through modes** — exploration, transition, development, and release.
6. **Prove** — supply replacement evidence and quality coverage, then pass the Release Gate.
7. **Complete** — apply the lifecycle changes to learned contracts and Ledger records, close the transition Plan, and preserve the final evidence.

## Four modes

### Exploration

Fast iteration and broad experimentation. Forge still protects secrets, data integrity, project identity, and packaging boundaries. Production release is blocked.

### Transition

Old and new systems may coexist. Migrations, compatibility bridges, asset conversion, and replacement contracts are tracked explicitly.

### Development

The new direction is selected. Implementation, tests, Labs, standards, accessibility, efficiency, performance, privacy, security, and UX evidence are completed.

### Release

All affected obligations have final dispositions. Required replacement evidence and quality coverage are present. The project can run release-grade proof.

## Obligation stability

Every obligation can identify both its kind and stability:

- **Enduring** — behavior or outcome that should survive the pivot.
- **Architecture-bound** — tied to the old implementation and usually eligible for retirement or replacement.
- **Temporary** — transitional requirement with an explicit end condition.
- **Experimental** — may be discarded without becoming permanent architecture.

Kinds include behavior, implementation, architecture, security, data, privacy, accessibility, compatibility, performance, efficiency, user experience, maintainability, integration, and standards.

## Contract dispositions

- **Retain** — remains active without changing its meaning.
- **Revise** — remains active with new evidence or a refined definition.
- **Suspend** — temporarily inactive, with a recorded reason.
- **Replace** — an identified successor takes over.
- **Retire** — deliberately removed because it no longer serves the product.
- **Restore** — a previously suspended or retired protection becomes active again.
- **Supersede** — historical authority is replaced by a newer decision or contract.

A destructive disposition requires a reason. Replacement and supersession require a successor. Revised and replaced obligations require evidence before release.

## Pre-pivot checkpoint

Activation creates a hash-verified checkpoint containing Forge configuration, Plans, Ledger records, learned contracts, the source-tree fingerprint, and the latest green Gate evidence.

Forge can restore that **assurance state** after a cancelled experiment. It does not claim to restore application source. Preserve source through version control or an internal Forge delivery.

## Quality and standards

The linked transition Plan tracks security, reliability, performance, efficiency, accessibility, user experience, maintainability, compatibility, and privacy. Each dimension must have evidence or be explicitly marked not applicable before Pivot can enter release mode.

Standards are versioned Ledger records with a source, authority, scope, version, review date, and replacement history. Forge does not pretend its bundled knowledge is always the current authority.

## Example

```json
{
  "title": "Move from 2D to 3D",
  "objective": "Replace the rendering architecture while preserving player-facing behavior and saved progress.",
  "entry_mode": "exploration",
  "changed_paths": ["game/renderer", "game/scenes", "game/save"],
  "obligations": [
    {
      "id": "OBL-CONTROLS",
      "title": "Player controls remain configurable",
      "kind": "behavior",
      "stability": "enduring"
    },
    {
      "id": "OBL-2D-RENDERER",
      "title": "Use the current 2D renderer",
      "kind": "architecture",
      "stability": "architecture-bound"
    },
    {
      "id": "OBL-SAVE-DATA",
      "title": "Existing save data remains readable or receives a verified migration",
      "kind": "data",
      "stability": "enduring"
    }
  ],
  "intentional_breakage": ["Old scene files will not remain runtime dependencies"],
  "migration_concerns": ["Save conversion", "Asset conversion"],
  "release_evidence": ["gate:release", "lab:save-migration", "lab:critical-gameplay"],
  "standards_refs": ["STAN-GAME-ACCESSIBILITY", "STAN-SECURITY"]
}
```

```bash
python3 Emotivus-Forge/forge.py change pivot . --action create --input pivot.json
python3 Emotivus-Forge/forge.py change pivot . --action assess --id <pivot-id>
python3 Emotivus-Forge/forge.py change pivot . --action classify --id <pivot-id> --input classification.json
python3 Emotivus-Forge/forge.py change pivot . --action activate --id <pivot-id>
python3 Emotivus-Forge/forge.py change pivot . --action mode --id <pivot-id> --mode transition
python3 Emotivus-Forge/forge.py change pivot . --action mode --id <pivot-id> --mode development
python3 Emotivus-Forge/forge.py change pivot . --action mode --id <pivot-id> --mode release
python3 Emotivus-Forge/forge.py prove gate . --level release --fresh
python3 Emotivus-Forge/forge.py change pivot . --action complete --id <pivot-id> --reason "Replacement verified"
```

## Completion boundary

Pivot completion requires:

- no unresolved dispositions;
- reasons for suspension, retirement, and supersession;
- known successors for replacement and supersession;
- replacement evidence for revised and replaced obligations;
- complete quality-evidence coverage;
- deliberate release mode;
- a current passing Release Gate;
- a recorded final source fingerprint.

This is how Forge supports ambitious change without confusing flexibility with unverified release.
