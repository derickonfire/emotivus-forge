# Cold Capability Vault

`capability_vault/manifest.json` is the authority for preserved legacy implementations. The public active-core capability registry is separate and contains no legacy code.

A capability may be reconnected only when all of the following exist:

1. a real project trigger;
2. a certified active implementation;
3. a project-owned activation contract;
4. a bounded runtime and context budget;
5. exact scope and exclusions;
6. focused neutral regressions;
7. evidence that the capability adds distinct value beyond the project’s native tool.

Forge Doctor is the first clean-room reconnection. The legacy Doctor and remediation code remain vaulted and are not imported by the active service.

The vault remains excluded from Help, Adopt, Resume, ordinary Check, Resume packets, automatic project scans, command registration, and public runtime packages.
