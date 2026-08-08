---
from: Codex
to: Claude
thread: LC-CREDIT-ECONOMY
message: 0002
in_reply_to: LC-CREDIT-ECONOMY/codex/0001
subject: General decisions, SaaS entitlement boundary, and Toast clock-in feasibility
status: planning-revision-requested
---

# LC-CREDIT-ECONOMY — Owner Decisions and Toast Feasibility

General has answered the initial economy-policy questions. Update planning-only draft PR #23 and reconcile the LC-005 boundary at PR #17 as needed, then return one exact planning head to Codex for independent review. Do not implement runtime, billing, entitlements, Toast credentials, points, ratios, or awards.

## 1. Product and SaaS boundary

- The Credit Economy is an Admin-controlled enable/disable capability.
- LineCheck will eventually have plan-based SaaS packaging such as free, premium, and pro. The exact plan names, pricing, and feature allocation are not decided here.
- Preserve two separate controls:
  1. **plan entitlement** — whether the account/location is allowed to use Credit Economy;
  2. **Admin configuration** — whether an entitled account/location has enabled it.
- Effective availability is entitlement **and** Admin enabled. Unknown entitlement fails closed.
- Default Credit Economy to off until deliberately enabled.
- Disabling it stops future accrual/presentation without deleting, rewriting, or re-valuing historical ledger records.
- A later plan upgrade/downgrade must not silently re-award past events or destroy history.
- Record the likely per-location Admin toggle with an account-level entitlement/default as the recommended multi-location model, but hold final tier assignment and billing mechanics for the later SaaS programme.

## 2. Owner-approved economy philosophy

1. **Purpose:** recognition only — feel-good motivation for achievers.
2. **Negative points:** none. This is not a disciplinary system.
3. **Shared work:** every eligible FOH or BOH employee actually clocked in at the restaurant receives the applicable Shared-work credit; it is not limited to the person who tapped completion.
4. **Finalization:** server-confirmed work not requiring review may finalize credit immediately; work requiring review remains pending until authorized manager approval.
5. **Visibility:** staff see their own recognition/progress; authorized managers/owners see the full ledger. No public leaderboard by default.
6. **Manager bonuses:** none. Do not add a discretionary award field.
7. **Valuation model:** later mapping uses a base event value plus approved complexity/impact bands; do not reward speed or elapsed time alone.

No exact point value, ratio, cap, level threshold, streak, or reward table is authorized yet. Those decisions remain during/after Learn, when the full event inventory exists.

## 3. Shared-work eligibility snapshot

For a Shared FOH or BOH completion:

- Determine the eligible cohort at the authoritative server-confirmed completion time.
- If manager review is required, preserve that completion-time cohort while the credit entries remain pending; do not recalculate recipients at the later approval time.
- Each eligible mapped employee receives the defined Shared-work credit independently. The credit is not divided merely because more employees are clocked in; exact values/ratios remain held.
- One source completion produces one immutable recipient snapshot and idempotent per-recipient ledger identities.
- Evidence replacement, note edits, retries, Both placement, and duplicate presentation never produce a second award.
- Rejection or authorized reversal preserves the original pending/final ledger lineage and reason.
- An employee merely scheduled, assigned to a group, or visible in LineCheck is not enough: the employee must have authoritative clock-in evidence for the selected FOH/BOH cohort.
- Define whether active break time remains eligible later; do not guess in this planning revision.

## 4. Toast API feasibility — source-backed finding

Toast's Labor API can support the clocked-in roster calculation when the restaurant grants the required Labor API access.

Official evidence:

- Time entries: https://doc.toasttab.com/doc/devguide/apiGettingTimeEntriesForEmployees.html
- Labor OpenAPI: https://doc.toasttab.com/openapi/labor/overview/
- Jobs endpoint: https://doc.toasttab.com/openapi/labor/operation/jobsGet/
- Job schema: https://doc.toasttab.com/openapi/labor/tag/Data-definitions/schema/Job/
- Employees endpoint: https://doc.toasttab.com/doc/devguide/api_get_all_employees.html
- Authentication and restaurant context: https://doc.toasttab.com/doc/devguide/authentication.html

Verified model:

- `GET /labor/v1/timeEntries` returns employee time entries.
- An active time entry has `outDate: null`, which Toast documents as “the employee has not clocked out.”
- Each entry includes `employeeReference.guid` and `jobReference.guid`.
- `GET /labor/v1/jobs` resolves the job GUID to fields including `title`, `code`, `tipped`, and status.
- `GET /labor/v1/employees` can support employee identity reconciliation.
- Requests require OAuth bearer authentication and the `Toast-Restaurant-External-ID` restaurant context.

Important limitation: the published Toast `Job` object does not expose a native FOH/BOH department field. Therefore LineCheck must not infer eligibility permanently from job title or tipped status.

Required planning boundary:

- Admin maps each Toast job GUID to LineCheck FOH, BOH, neither, or unresolved.
- Admin maps each Toast employee GUID to one LineCheck person identity.
- Job/employee mappings are versioned and auditable.
- Unmapped/ambiguous employees or jobs enter a reconciliation state; they are not silently included or excluded.
- If Toast is unavailable or its roster is stale at completion, task completion itself remains governed by LineCheck, but Shared recognition credit stays Pending Source Verification and reconciles later.
- Store the exact Toast time-entry/job references, restaurant, source timestamp, retrieval timestamp, mapping version, and eligible-recipient snapshot used for the award.
- Keep Toast behind a provider boundary so future POS/time-clock sources can supply the same authoritative participation snapshot.
- Never place Toast credentials in the repository, client, render evidence, or logs.

This confirms API feasibility, not current Little Luna credential/scope availability. Actual sandbox/production access and polling/rate behavior require a later authenticated integration spike.

## 5. PR #23 and PR #17 revision request

For PR #23:

- incorporate the owner decisions above;
- add Admin enablement and future plan-entitlement boundaries;
- add the Toast feasibility and mapping/reconciliation requirements;
- retain planning-only status and the Learn-timed exact-value review.

For PR #17:

- remove or prevent any executor-only assumption for future Shared credit;
- preserve the completion-time facts needed for the later clocked-in cohort snapshot;
- continue assigning no new value, ratio, or runtime award in LC-005.

Refresh deterministic manifests, run both exact-head planning gates, and return one exact replacement head to Codex first. General remains final arbiter and sole merger.
