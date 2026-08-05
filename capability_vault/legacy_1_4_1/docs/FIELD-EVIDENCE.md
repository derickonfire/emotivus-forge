# Field Evidence

Forge public claims should be grounded in retained reports and described at the correct scope. These are early field results, not a claim that Forge has already been validated on every stack or production environment.

## Mature PHP and MariaDB application

The host had an established multi-tool gate, extensive runtime assertions, and a real-database migration harness.

Forge produced two material wins during its v1.0.5 integration:

1. It independently inventoried a valid privacy checker that existed but had not been registered in the host project's gate. The project had proved the checker manually but could still ship without enforcing it.
2. It rejected a false-green host run that exited successfully and printed PASS while the required migration evidence was absent because a fast profile skipped the database harness.

This demonstrated that Forge can supervise the completeness and evidence of an existing assurance system rather than merely duplicate its checks.

The named source report is retained outside the neutral public distribution in the private development record.

## Custom PHP deployment-package reintroduction

Forge v1.1 was introduced beside a 143-file deployment package without modifying any original application file.

Forge correctly detected the PHP, Apache, CSS, and JavaScript stack, read the application version, preserved audit-only handling of existing tools, produced portable state, and blocked release status because no new release target existed.

The field run also exposed improvements Forge still needs:

- Distinguish deployment packages from complete development source immediately.
- Enforce environment-parity evidence when the available PHP or database differs from production requirements.
- Separate source-tree proof from final-package proof.
- Record the authority and retirement lifecycle of temporary supplemental tooling.
- Generate only canonical portable v1.1 commands.

The named source report is retained outside the neutral public distribution in the private development record.

## Complete development-source reintegration and acceptance rehearsal

A later run used the complete development workspace rather than only the deployment artifact. Forge correctly identified the project stack and version, preserved the host project's mature release runner as authoritative, registered it without absorbing or replacing application code, and independently agreed with the host gate that the available PHP runtime was below the declared production requirement.

The combined audit exposed two development-handoff defects: the deployment package alone could not reconstruct the previously certified development tree, and a contradictory ignore rule would have omitted documentation from a future package. These findings informed Forge's workspace-provenance, source-completeness, packaging-policy reconciliation, and evidence-boundary hardening.

An acceptance-only rehearsal also demonstrated the importance of explicit work mode. The canonical scope approved staging and deployment validation but no new feature coding. Forge preserved that distinction while the host tools proved evidence-required acceptance states, credential redaction, contract-fingerprint invalidation, read-only reconciliation, and phase-aware migration cleanup. Forge treats these as design evidence, not as universal capabilities it may claim without implementing and testing them itself.

## Publication rule

A public claim must name what Forge found or proved, identify the project context, and avoid implying universal coverage. New field data should refine the product and roadmap before it is promoted as a win.

## Full-source and acceptance rehearsal lessons

A later complete-development-source reintegration confirmed that Forge can preserve an existing mature release runner as authoritative, register it into Forge Gates without absorbing or modifying application code, and independently agree with the host system on an environment-parity blocker.

The same field cycle exposed durable product requirements now implemented in Forge: workspace provenance, source completeness, approved work mode, project identity, packaging-policy reconciliation, evidence boundaries, and reduced duplicate execution.

An offline acceptance rehearsal also confirmed reusable assurance patterns: every acceptance item begins pending; completion blocks until all required items are resolved; pass/fail/blocked records require evidence; credential-shaped text is redacted; a changed application contract invalidates stale acceptance evidence; reconciliation remains read-only; protected paths are explicit policy; and migration-file lifecycle depends on the deployment phase.

These reports support Forge's direction but do not imply that Forge itself discovered or automatically repaired every host-project issue. Forge's durable role is to preserve, measure, enforce, and evidence the work while the active human or AI reasons about the repair.

## Live-runtime false-green correction

A field application returned HTTP `200` while rendering an unconfigured error body. A status-only Forge Lab accepted the transport response even though the application was not ready. Live multi-request testing also found a fresh-install defect that static lint and review had missed.

v1.2.1 converts those findings into neutral product safeguards:

- Status-only probes are labeled `connectivity-smoke`.
- Section and Release Labs require at least content-readiness by default.
- Body, negative-body, content-type, header, size, URL, and JSON assertions are supported.
- Ordered journeys retain cookies and captured response state.
- Missing configuration, environment variables, executables, files, or services return `BLOCKED`.
- Reports retain readiness fingerprints and explicit evidence boundaries.

The lesson is permanent: static correctness, endpoint availability, application readiness, and stateful behavior are different claims and require different evidence.


## Authorization-management lesson

A later admin-permission review reinforced that static permission maps do not prove runtime authorization administration. A project must separately verify who can grant, revoke, or escalate privileges; whether self, peer, or superior targets are allowed; whether direct URLs and denied mutations remain blocked; whether CSRF and explicit-deny precedence hold; and whether existing sessions lose access after suspension or revocation.

v1.3 implements this as neutral, explicit authorization contracts. The public claim is intentionally scoped: Forge validates the declared behavioral matrix and retained evidence; it does not infer the product's intended hierarchy or declare a project secure from source strings alone.
