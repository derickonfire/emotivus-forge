# Session Close

Session Close is an explicit option on **Check**. It records the handoff needed by the next development session without adding a sixth public command or a ninth top-level state file.

## Recommended close

```bash
python3 Emotivus-Forge/forge.py check . \
  --checkpoint \
  --close-session \
  --session-type code-increment \
  --summary "Completed the bounded authentication increment." \
  --completed "Added the login route." \
  --decision "Keep authentication local-first::Avoid a new hosted dependency." \
  --owner-fact "The project must remain portable::Do not require Git or a hosted service." \
  --risk "Browser behavior has not been verified." \
  --next-action "Run the login flow in the browser fixture."
```

Use `--checkpoint` only when the scoped Check passes and the current snapshot should become the accepted baseline. Session Close can still record a failed audit or Check; the failure and unresolved risks remain visible in Resume.

## Session types

- `code-increment`
- `decision-checkpoint`
- `audit`
- `release-candidate`
- `deployment`

The type records what happened. It does not upgrade the assurance claim. A `release-candidate` or `deployment` Session Close is still not Ship certification.

## Durable fields

Session Close records:

- completed work;
- reconciled changed files;
- accepted decisions and rationale;
- owner-confirmed project facts and their design impact;
- Check result, findings, native-gate status, and evidence reference;
- unresolved risks;
- one exact next action;
- a bounded fingerprint of the observed project state.

Decisions use `DECISION::RATIONALE`. Owner facts use `FACT::IMPACT`. Do not put credentials, secret values, personal data, or production tokens into Session Close.

## Continuity status

Resume reports the latest handoff as:

- `current` — the observed project state matches the latest Session Close;
- `stale` — files changed after the latest Session Close;
- `not-established` — first adoption has no prior Session Close yet;
- `missing` — continuity previously existed but its expected handoff is unavailable.

The latest exact next action outranks an inferred next action, but it does not replace the project’s confirmed objective.

## Optional interaction telemetry

Session Close may also retain:

- provider-reported input and output tokens with the provider name;
- observed retry and correction counts;
- observed assistant-output characters;
- a matched benchmark ID and `with-forge` or `without-forge` arm.

```bash
python3 Emotivus-Forge/forge.py check . \
  --close-session \
  --next-action "Continue the matched task." \
  --provider "Example Provider" \
  --provider-input-tokens 1200 \
  --provider-output-tokens 300 \
  --retry-count 1 \
  --correction-count 0 \
  --benchmark-id auth-flow-01 \
  --benchmark-arm with-forge
```

Input and output token counts must be supplied together. A benchmark arm requires exact provider counts. Forge treats these values as exact only because the operator supplied them from the named provider; it does not infer or verify provider usage.


## Portable continuity companion

After a meaningful Session Close, `--export-continuity` creates a separate project-private continuity ZIP. Add `--development-package` to bind the companion to the exact development package digest. The bundle stays outside deployable application files and may be restored through Adopt. See `CONTINUITY-HANDOFF.md`.

## Resume refresh

In Forge 0.543, a successful Session Close regenerates compact `.forge/resume.md` automatically. The operator does not need a separate Resume command merely to expose the just-closed session.
