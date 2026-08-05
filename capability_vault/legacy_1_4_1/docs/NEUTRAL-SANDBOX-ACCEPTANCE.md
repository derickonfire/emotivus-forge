# Neutral Sandbox Acceptance — Forge v1.3.4

## Purpose

This acceptance exercise uses a newly constructed PHP 8.4 operations portal rather than any named internal application or historical product snapshot. The scenario is retained as a reproducible companion package, and its confirmed defects are represented by permanent project-neutral regressions.

## Scenario perimeter

Harbor Operations contains seven executable obligations:

- three browser pages;
- one API endpoint;
- one webhook;
- one scheduled job; and
- one CLI command.

The negative branch also contains a blank HTTP 200 response, an incompatible prior persisted state, a broken migration result, a missing required `gd` extension, unsupported verification claims, a stale generated changed-files archive, and no final owner-facing bundle.

## Negative branch result

Forge v1.3.4 returned FAIL and reported:

- 7 discovered surfaces, 0 covered;
- target-environment evidence absent, stale, or not produced by the current registered Gate command;
- prior-state-plus-current-code evidence absent, stale, or not produced by the current registered Gate command;
- the required `gd` extension uncovered;
- generator command, receipt, and input drift for `release/Changed-Files.zip`; and
- `final owner-facing delivery bundle has not been built`.

Delivery verification returned an actionable problem list rather than an unexplained FAIL. Graph contained one webhook identity, and `assets/app.js` remained supporting source rather than an executable entrypoint.

## Remediated control result

After the application obligations were genuinely corrected and the current inner artifact was recorded:

- Release Proof showed 7 of 7 surfaces covered;
- target-environment and deployment-state dimensions passed;
- delivery provenance correctly remained FAIL only because the final outer bundle had not yet been built;
- that delivery problem did not become a claim blocker or prevent the build action;
- the Release Gate passed; and
- Forge built and verified the exact final owner-facing handoff.

The retained machine evidence records the exact SHA-256 of the handoff produced by that run.

Final coverage and delivery verification both returned PASS with no problems or limitations.

## Additional assurance correction

During the control run, refreshing an inner artifact exposed that an existing outer ZIP could otherwise remain apparently current. v1.3.4 now invalidates the final bundle whenever a registered artifact is refreshed and verifies the current SHA-256 of every declared member inside the ZIP. Duplicate member paths, missing members, and stale member bytes fail delivery verification.

## Boundary

This neutral acceptance proves the recorded synthetic scenario and the associated permanent regressions. It does not replace the broader license-verified external corpus required for v1.5.
