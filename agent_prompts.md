# Agent Council Scoring Prompts

The council layer simulates independent perspective review. Each perspective uses deterministic prompts below.

## Planner perspective
- Focus on timeline quality and action completeness across 24h / 6h / 1h.
- Prioritize whether actions are sequenced to reduce ambiguity for local teams.
- Return a score on readiness vs execution trade-off.

## Risk analyst perspective
- Focus on risk intensity from forecast and hazards.
- Score whether actions are activated early enough for the given hazard window.
- Penalize plans that under-react under high flood score.

## Operations perspective
- Focus on feasibility and workload with known resource inventory.
- Score the ability to execute within ETA assumptions.
- Reward tasks that reduce dispatch ambiguity and duplication.

## Community safety perspective
- Focus on vulnerable care, comms accessibility, and equitable coverage.
- Reward inclusion of multilingual messaging and explicit vulnerable support.
- Penalize missing welfare checks and weak evacuation routes.

## Merge rule
- Final rank = weighted average of all four scores.
- Contradiction summary should note significant score divergence greater than 0.25.
- Always include assumptions section for each recommendation.
