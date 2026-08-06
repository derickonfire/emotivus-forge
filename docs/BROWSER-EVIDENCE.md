# Exact Browser Viewport Evidence

Forge 0.549 adds a bounded browser-executed evidence instrument for one exact static website ZIP.
It is a release-certification aid, not a new public command and not an accessibility or device lab.

## Run

```bash
python3 tools/run_browser_evidence.py run \
  --website deploy/Emotivus-Forge-0.549-Website.zip \
  --browser /path/to/chromium \
  --output-dir release/browser-evidence/0.549 \
  --bundle deploy/Emotivus-Forge-0.549-Browser-Evidence.zip
```

The tool safely verifies and extracts the website ZIP, records the exact browser executable and
external Playwright driver identity, renders six public routes under fixed desktop-light and
viewport-shaped dark profiles, and captures content-addressed DOM, screenshot, resource, console,
exception, request-failure, color-scheme, viewport, and horizontal-overflow evidence.

Playwright is an optional external execution dependency. Forge does not bundle it, download it, or
manage browsers. The receipt records its installed version and the exact browser binary digest.

## Network boundary

Some managed Chromium environments block all URL navigation, including loopback. The instrument does
not bypass that policy. It loads each exact route HTML from the extracted package with
`page.set_content`, injects one package-local base URL, fulfills only package-relative CSS, JavaScript,
and image requests from the same extracted root, and blocks every external request.

A PASS therefore proves browser rendering of exact package bytes under network-isolated package
routing. It does not prove HTTP-server behavior, production-origin behavior, redirects, headers,
TLS, CDN behavior, remote availability, or deployment.

## Truth boundary

A browser-evidence PASS is not evidence of:

- a physical phone, tablet, or desktop device;
- touch or pointer interaction;
- assistive-technology compatibility or accessibility conformance;
- manual visual correctness;
- production-origin or remote-network behavior;
- independent review or a named human acceptance decision;
- owner authorization, release authorization, or release readiness.

The exact evidence bundle can be verified later with:

```bash
python3 tools/run_browser_evidence.py verify \
  --bundle deploy/Emotivus-Forge-0.549-Browser-Evidence.zip \
  --website-sha256 <exact-website-zip-sha256>
```
