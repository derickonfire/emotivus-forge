# Adapters

## PHP

Runs PHP CLI syntax checks when available and supports the bundled structural and regular-expression tools through project commands. Runtime version checks are project-configurable.

## JavaScript and Node.js

Runs `node --check` for executable JavaScript. During initialization, detected package scripts are added using npm, pnpm, Yarn, or Bun based on the project lockfile. Additional build and verification ecosystems can be adopted through manifest-backed tool integration; standalone commands remain available only when no authoritative runner already owns them.

## CSS

Checks balanced block structure. Projects may opt into the selector-to-markup wiring ratchet with `tools/check_css_wiring.py`.

## Apache/cPanel

Tracks `.htaccess` evidence and lets projects make hardening files mandatory in deployment packages. Live directive behavior remains a staging responsibility.

## Python

Compiles Python source and can run configured unittest or pytest commands.

Adapters are deliberately modest. Framework-specific behavior belongs in project commands or a private project policy pack rather than in universal core logic.
