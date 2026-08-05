# Forge Lab

Forge Lab runs disposable verification recipes without confusing process startup, HTTP availability, application readiness, stateful behavior, or production equivalence.

## Evidence levels

Every Lab report declares the strongest claim it actually proved:

1. `process-started` — a process started; no readiness claim.
2. `connectivity-smoke` — an endpoint returned an expected transport status.
3. `content-readiness` — status plus declared body, header, content-type, size, URL, or JSON assertions passed.
4. `stateful-behavior` — an ordered journey passed while preserving cookies and captured response state.
5. `environment-backed-behavior` — declared behavior passed with the listed executables, files, environment variables, and services present.
6. `release-equivalent` — the project explicitly approved the environment as release-equivalent.

A status-only HTTP 200 is never described as application readiness. By default, Section and Release Gates require at least `content-readiness` for assigned Lab recipes.

## Safe defaults

- Copies the project to a temporary workspace
- Excludes Forge state, deployment output, Git data, internal configuration, `__pycache__`, and Python bytecode
- Refuses symbolic links in the copied source
- Allocates an ephemeral localhost port
- Checks declared prerequisites before setup
- Runs optional setup commands
- Starts a local service
- Repeats readiness probes until the startup deadline
- Runs ordered stateful journeys with a shared cookie jar
- Captures declared response values without storing their secret values in reports
- Runs optional verification and teardown commands
- Terminates the service process group
- Removes the workspace after success
- Records JSON and text evidence with readiness fingerprints

## Plan

```bash
python3 Emotivus-Forge/forge.py prove lab . --action plan
```

Forge safely infers basic static-site and PHP **connectivity** recipes. A project must add content or behavioral assertions before those recipes can satisfy stronger Gate evidence.

## Run

```bash
python3 Emotivus-Forge/forge.py prove lab . --action run --recipe application-readiness
```

Add `--preserve` when investigating a failed Lab and the temporary workspace should remain available.

## Content-aware readiness probe

```json
{
  "id": "application-readiness",
  "profiles": ["release"],
  "workspace": "copy",
  "evidence_level": "content-readiness",
  "prerequisites": {
    "executables": ["php"],
    "files": ["config.php"],
    "env": ["APP_TEST_DB_URL"]
  },
  "start": ["{php}", "-S", "127.0.0.1:{port}", "-t", "{workspace}"],
  "probes": [
    {
      "url": "http://127.0.0.1:{port}/",
      "expected_status": [200],
      "expected_content_type": "text/html",
      "contains": ["Expected Product Name"],
      "not_contains": ["not configured", "fatal error"],
      "min_bytes": 1000,
      "required_headers": {"Cache-Control": "no-store"}
    }
  ]
}
```

Supported response assertions include:

- `contains`, `not_contains`
- `body_regex`, `not_body_regex`
- `expected_content_type`
- `required_headers`, `forbidden_headers`
- `min_bytes`, `max_bytes`
- `expected_final_url`
- `json_assertions`

Reports retain hashes, assertion results, observed header names, response size, final URL, and a readiness fingerprint. They do not store the full response body.

## Stateful journey

Journey steps run in order and share cookies. A step can capture a value by regular expression or JSON path, then reference it as `{state:name}` later.

```json
{
  "id": "fresh-install-journey",
  "profiles": ["release"],
  "evidence_level": "stateful-behavior",
  "journey": [
    {
      "id": "open-installer",
      "url": "http://127.0.0.1:{port}/install",
      "expected_status": [200],
      "body_regex": "name=\"csrf\" value=\"[^\"]+\"",
      "capture": {"csrf": {"regex": "name=\"csrf\" value=\"([^\"]+)\""}}
    },
    {
      "id": "submit-installer",
      "method": "POST",
      "url": "http://127.0.0.1:{port}/install",
      "form": {"csrf": "{state:csrf}", "site_name": "Fixture"},
      "expected_status": [200],
      "contains": "Installation complete",
      "not_contains": "already installed"
    }
  ]
}
```

Forge preserves HTTP state and proves only the declared journey. Database contents, provider delivery, and production-host behavior need their own verification commands or external evidence.

## Prerequisite contract

A recipe can require:

- `executables`
- `env`
- `files`
- `services` with host and port

Missing prerequisites produce `BLOCKED`. They never become PASS and never silently reduce the evidence level.

## Boundary

Forge Lab proves behavior inside the declared environment and assertions. It does not infer production equivalence from localhost, substitute HTTP status for application readiness, or claim real provider delivery without matching evidence.
