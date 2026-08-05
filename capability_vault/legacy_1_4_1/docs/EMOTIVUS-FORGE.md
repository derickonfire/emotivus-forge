# Emotivus Forge

Emotivus Forge is an internal, project-neutral system for preserving engineering decisions across human and AI-assisted development sessions.

Its purpose is not to replace compilers, linters, test frameworks, CI systems, browsers, databases, or external integration testing. It coordinates those tools, adds invariant checks and deployment controls, records evidence, and prevents known classes of release failure from being forgotten.

## Core principles

- Audit before governance.
- Preserve project-specific tools until redundancy is proven.
- Convert confirmed defects into durable regressions.
- Keep blockers non-baselinable.
- Separate inherited debt from newly introduced defects.
- Require explicit release state before production packaging.
- Treat packaging as a security boundary.
- Make every automated claim inspectable in JSON and plain text.
- Record live checks that static analysis cannot prove.
