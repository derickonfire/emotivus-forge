# Bounded Session Sidecar

Forge stores a compact observational sidecar status in the existing `.forge/state.json` file. No ninth top-level state file is added.

The record can show:

- development-sidecar, evidence-analysis, or release-assessment mode;
- current work scope;
- authority-baseline status;
- unexpected mutation count;
- latest scoped Check status and time;
- latest Ship assessment status.

Resume returns to development-sidecar mode. An audit Session Close can place Check in evidence-analysis mode. Explicit Ship records release-assessment mode.

The sidecar is not a daemon. It does not inspect every conversation message, run in the background, authenticate authorship, change authority, merge files, or authorize release. Its purpose is to make Forge’s current operating posture visible and compact.
