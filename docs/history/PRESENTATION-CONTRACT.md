# Cross-Model Presentation Contract

Forge 0.525 can preserve an owner-approved communication structure across ChatGPT, Claude, and other AI agents without storing long example responses in routine context.

```bash
forge adopt . --record-presentation-profile forge-presentation-profile.json
forge resume .
```

The contract can define:

- owner, builder, and expert audience layers;
- owner-first or builder-first default output;
- section order;
- compact, standard, or detailed verbosity;
- technical-detail placement;
- table and bullet preferences;
- scoped PASS language;
- meaningful-only Forge-line behavior.

Resume carries one compact instruction. The full contract stays in local Forge state. The active AI model still authors the prose, so Forge cannot guarantee identical elegance, wording, or judgment across models.
