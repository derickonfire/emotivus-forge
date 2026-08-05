# Workspace provenance and scope

Forge 1.1.1 identifies whether it received complete development source, a deployment artifact, an internal delivery, a release candidate, a reconstructed tree, or an incomplete workspace. It records which planning, release, testing, and tooling authorities are present before broad work begins.

Forge also detects the active work mode. An acceptance-only handoff does not silently become permission to write features. The owner or canonical project plan remains authoritative.

Runtime requirements are derived from project metadata when possible. Doctor distinguishes useful static verification from release-equivalent environment parity.

Evidence is labeled by boundary: development-source evidence does not automatically certify the packaged artifact, and package evidence does not imply the complete development source was present.
