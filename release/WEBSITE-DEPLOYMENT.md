# Website Deployment — Forge 0.552

1. Build and certify `RUN-FORGE-0.552.zip` first.
2. Generate `docs-site/downloads/SHA256SUMS.txt` from the exact runtime and current release notes.
3. Regenerate the four-page site from `FORGE-PRODUCT.json`.
4. Prove the embedded `RUN-FORGE.zip` is byte-identical to the standalone public runtime.
5. Run local link and exact browser-evidence verification before deployment.

Deployment remains external to Forge and is not implied by package certification.
