# Forge Token Conservation

Token conservation is a primary product benefit of Forge, especially for large projects and repeated AI handoffs.

## The problem

Without durable project memory, each new AI session often rereads broad portions of the repository, reconstructs architecture, reloads old plans, repeats decisions, and spends context discovering work that previous sessions already understood. As projects grow, this consumes tokens while still producing inconsistent understanding.

## Forge's mechanism

Forge separates durable project truth from task-specific context:

1. **Adopt** builds the Project Passport, structure inventory, continuity records, uncertainties, and file checkpoint.
2. **Resume** retrieves only the minimum sufficient verified truth for the current objective.
3. **Check** updates changed paths, impact, evidence, and the Passport so later sessions do not start from stale context.
4. **Ship** binds the delivery artifact to exact proof rather than requiring another broad reconstruction.

## Measurement

Resume reports:

- `packet_estimated_tokens`;
- `packet_token_limit`;
- `project_token_equivalent_estimate`;
- `estimated_tokens_avoided`;
- `estimated_context_reduction_percent`;
- the estimation method and truth boundary.

The project baseline currently uses snapshot bytes divided by four. This is intentionally simple, reproducible, and provider-neutral. It is not an exact tokenizer result, billing estimate, prompt-cache claim, or guarantee of savings.

## Safety rule

Forge conserves tokens through precision, retrieval, durable memory, and elimination of repeated reconstruction. It must never conserve tokens by omitting material uncertainty, active risks, migration state, security findings, required evidence, or decisions needed for the current task.

## Product promise

Forge should make the next AI session smaller and better informed than a fresh whole-project upload—not merely smaller.
