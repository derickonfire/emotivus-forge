# Traceable Bounded Retrieval

Resume can retrieve a small, traceable set of current project records without storing raw conversations, requiring embeddings, or changing authority.

```bash
forge resume . --query "exact parent package and unresolved browser evidence"
```

Retrieval currently considers:

- governed continuity facts;
- open knowledge gaps;
- latest Session Close decisions;
- latest owner facts;
- unresolved risks;
- the exact next action;
- recent Ledger events.

It combines exact stable-key matching, normalized technical-token similarity, authority and support status, blocker urgency, and Reciprocal Rank Fusion. Near-duplicates retain the higher-trust, currently supported record. Owner facts, exact next actions, blocker gaps, and unresolved risks do not silently fade because a query is unrelated.

Each returned record includes:

- stable identity and record kind;
- trust level;
- support status;
- bounded selection reasons;
- exact Ledger or project-file support references when available;
- a bounded one-hop relationship trace.

## Boundaries

Retrieval relevance is not authority. Similarity, frequency, recency, ranking, and graph proximity cannot change facts, support validity, project baselines, Check state, or release claims. The operation is read-only except for the ordinary observational Resume sidecar and telemetry already produced by Resume.
