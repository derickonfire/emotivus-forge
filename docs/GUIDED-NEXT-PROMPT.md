# Guided Next Prompt

Run Forge returns one bounded, copy-ready continuation prompt so a non-technical user does not have to translate Forge findings into instructions for the AI agent.

## Output contract

JSON includes:

```json
{
  "recommended_prompt": {
    "schema": 1,
    "label": "Forge recommends this prompt",
    "text": "Continue this project from the exact next action: …",
    "copy_ready": true,
    "kind": "continue-project",
    "max_characters": 680,
    "truth_boundary": "…"
  }
}
```

Human output includes one line:

> **Forge recommends this prompt —** Continue this project from the exact next action: …

## Decision rules

- A blocker tells the AI to stop before changing the project and resolve the blocker first.
- An unconfirmed objective tells the AI to verify the authoritative roadmap before coding.
- A confirmed next action becomes the continuation target.
- Pending decisions remain owner- or project-authority decisions.
- Native checks remain limited to their recorded execution authority.
- Meaningful work ends with Forge Session Close.

## Token boundary

The recommendation is capped at 680 characters. It does not copy full attention lists, evidence logs, relationship maps, hashes, or authority traces into chat. Those remain in local structured state and can be opened only when needed.

## Trust boundary

This is workflow guidance, not autonomous authority. It cannot override project rules, approve a native gate, resolve a decision fork, certify a PASS, or permit destructive work.
