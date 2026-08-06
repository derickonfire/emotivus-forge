# Bounded Ship Claim Levels

Forge 0.543 reports a cumulative claim ladder. Every level requires all earlier levels; a lower PASS never implies a higher claim.

1. **continuity-ready**
2. **checkpointed-candidate**
3. **authority-recorded-candidate**
4. **lineage-identified-candidate**
5. **migration-history-identified-candidate**
6. **package-family-identified-candidate**
7. **surface-coverage-mapped-candidate**
8. **native-verified-candidate**
9. **release-facts-current-candidate**
10. **runtime-content-verified**
11. **persisted-state-assured**
12. **final-package-bound**
13. **confidentiality-screened**
14. **public-release-reviewed**
15. **artifact-signature-verified**
16. **release-channel-bound**
17. **remote-channel-verified**
18. **release-proof-validated**
19. **cold-session-validated**
20. **owner-release-authorized**
21. **release-ready**

`continuity-ready` additionally requires a current governed continuity register and no open knowledge gap explicitly scoped to block Ship or release. A remembered fact does not create authority.

`authority-recorded-candidate` requires an exact project-authority baseline for the unchanged tree and a later passing Check.

`lineage-identified-candidate` additionally requires one current exact lineage record and no unresolved same-version incoming branch collision.

`migration-history-identified-candidate` additionally requires one current exact migration catalog or explicit no-migrations declaration, with no unresolved identity collision or sequence-only body-unknown applied testimony.

`package-family-identified-candidate` additionally requires one current exact package family, an exact result artifact equal to the lineage tree, exact outer-bundle members, and deterministic declared delta reconstruction.

`surface-coverage-mapped-candidate` additionally requires one current surface inventory bound to the exact result artifact and current explicit PASS evidence at every surface’s project-declared required tier. Route existence does not prove database, authenticated, browser, device, staging, production, or deployment behavior. Higher tiers do not silently fill other tiers.

`release-facts-current-candidate` additionally requires one current exact-package fact set after native verification, with every declared visible document field matching its current canonical value and no declared forbidden legacy text. Arbitrary prose and undeclared documents remain outside the claim.

The later native, runtime, persisted-state, exact-package, distribution, Release Proof, cold-session, and authorization levels retain their existing bounded meanings. `release-ready` passes only when every cumulative claim is current and remains a statement about one assessed package and declared evidence—not universal correctness or release permission invented by Forge.
