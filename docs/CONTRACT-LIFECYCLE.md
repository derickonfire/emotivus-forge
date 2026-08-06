# Shared Contract Lifecycle

Forge uses one fingerprint-bound lifecycle rule for project-owned capabilities, guardrails, field trials, project identity, Ledger assertions, and check qualifications:

```text
proposed → active → approval-required → retired
```

Public compatibility fields may still use specific terms such as `reactivation-required`, `rerecord-required`, or `reapproval-required`. Their normalized `lifecycle_status` is `approval-required`.

## Rules

- A project-owned source becomes active only after an explicit authority action.
- The normalized content and exact source bytes are fingerprinted.
- A missing or changed source cannot remain silently active.
- Changed records require renewed authority; Forge does not infer acceptance.
- Retirement preserves the original event and the retirement rationale in the Ledger.
- Lifecycle status proves authority and source currency only. It does not prove that the contract itself is correct.

Native-gate approvals expose the same lifecycle meaning: detected candidates are proposed, fingerprint-bound approvals are active, and changed commands require approval again.

Ledger assertion and check-qualification records use the same source-currency rule: a changed or missing project-owned contract becomes `approval-required`; retired records remain in history but no longer enforce or qualify current evidence.
