# Forge Self-Hosting Contract

This directory contains the durable, version-controlled invariants used when Forge Mirror certifies Forge itself. These contracts are intentionally separate from temporary `.forge/` state and are included in every Forge distribution.

Mirror copies Forge into an isolated workspace, points Forge Learn at `self/learned-contracts.json`, and requires every active contract to pass before distribution packaging.
