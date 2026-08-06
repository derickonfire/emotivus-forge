# Legacy State Migration

Forge detects a legacy `.forge/passport/passport.json` and preserves accepted, active, or resolved records from `.forge/project/ledger.json` in the new append-only Ledger.

Migration is one-way and non-destructive:

- legacy state remains in place;
- accepted records are copied with migration provenance;
- pending or unconfirmed legacy notes are not silently promoted;
- confirmed authority and native-gate state created by the new core persist independently.

Migration does not certify application database migrations or production persisted-state compatibility.
