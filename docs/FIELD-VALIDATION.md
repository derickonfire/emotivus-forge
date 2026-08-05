# Field Validation

Forge field validation exists to test whether the product improves real development work. It does not allow Forge to score itself or turn a small local sample into a universal product claim.

## Evidence model

A field trial has two project-owned inputs:

1. a **trial contract** recorded through Adopt;
2. one or more **observations** supplied by a human reviewer or controlled fixture and linked to Session Close.

Both inputs must remain ordinary project files outside `.forge/` and outside the Forge distribution.

## Record a trial plan

Copy `examples/field-trial.example.json` into the target project and replace its sources, models, scenarios, and measures with real project facts.

```bash
python3 Emotivus-Forge/forge.py adopt . \
  --record-field-trial forge-field-trial.json
```

The schema-1 contract requires:

- a stable lowercase `trial_id`;
- title, authority, and rationale;
- a project profile;
- declared AI model labels and trial scenarios;
- project-owned ground-truth paths;
- a minimum observation count;
- supported measures;
- an explicit truth boundary.

Changing or deleting the trial contract prevents new observations until the authority records the current contract again.

## Record one observation

Create an observation from `examples/field-observation.example.json`, then link it to an explicit Session Close:

```bash
python3 Emotivus-Forge/forge.py check . \
  --close-session \
  --summary "Completed the bounded continuation trial." \
  --next-action "Run the next declared field scenario." \
  --field-observation field-observation-001.json
```

An observation identifies the trial, task, scenario, model, reviewer, and reviewer role. Supported reviewer roles are:

- owner;
- human reviewer;
- external reviewer;
- controlled fixture.

## Supported measures

Field observations can record:

- objective recovery: correct, partial, incorrect, or not measured;
- authority discovery: correct, partial, incorrect, or not measured;
- Resume usefulness score from 1–5;
- owner comprehension score from 1–5;
- activation/guardrail contract usability score from 1–5;
- time to meaningful work in minutes;
- native evidence ingestion: complete, partial, missed, not applicable, or not measured;
- Doctor ground truth, recommendation result, and diagnosis rating;
- guardrail ground truth and trigger result;
- project evidence paths and reviewer notes.

## Aggregation

Resume and JSON output summarize only the active project-local sample:

- observation count and minimum sample status;
- observed objective and authority correct rates;
- score averages and medians;
- time-to-meaningful-work averages and medians;
- Doctor and guardrail true positives, true negatives, false positives, and false negatives;
- precision and recall when denominators exist.

## Truth boundary

Forge validates structure, links observations to a Session Close, rejects duplicate IDs, and performs arithmetic. It does not independently verify reviewer judgment, establish causality, prove that Forge created an observed outcome, generalize across projects, establish commercial value, or provide release assurance.

Field evidence and exact provider-token telemetry are separate evidence classes. They may be reviewed together, but one cannot silently substitute for the other.
