# Difficulty Guidelines

Task difficulty is determined by pass rate when run against frontier AI models.

## Difficulty Levels

| Difficulty | Accuracy Target | Description |
|---|---|---|
| Hard | Accuracy <= 20% on the best model, or <= 20% on the worst model | Deep expertise, multi-step reasoning, or niche knowledge |
| Medium | 20% < accuracy <= 60% on the worst model | Moderate complexity and some domain knowledge |
| Easy | 60% < accuracy <= 80% on the worst model | Straightforward but still non-trivial |

Tasks where the worst model scores above 80% will not be accepted.

Current diversity requirements block easy tasks for new submissions, so target medium or hard.

## Best vs Worst Model

Both models are evaluated on every task:

- GPT-5.2 with Codex agent
- Claude Opus 4.6 with Claude Code agent

The worst model sets the difficulty floor for most tasks. If even the weaker model solves the task most of the time, the task is too easy.

The best model matters for hard tasks: if the strongest model still only scores <= 20%, the task is hard.

## Evaluation Process

Final evaluation uses 5 runs per model.

During development, run each model at least 2-3 times for an early estimate, then use 5 runs if you are near a threshold.

## Designing for Hard

Hard tasks often include:

- deep domain expertise
- 10+ meaningful sequential steps
- subtle debugging
- niche tools or languages
- obscure but available documentation
- bespoke rules mixed into familiar patterns

Good hard-task techniques:

- require root-cause analysis
- use domain-specific knowledge
- include realistic edge cases
- require careful artifact verification

## Designing for Medium

Medium tasks often include:

- 5-10 meaningful steps
- some domain knowledge
- clear requirements
- non-obvious implementation
- configuration details that are easy to miss

## Avoid Unfair Difficulty

Bad failure causes:

- impossible requirements
- ambiguous instructions
- time-dependent output
- external dependencies
- flaky environment
- tests that are stricter than the prompt

Good failure causes:

- reasoning mistakes
- missed edge cases
- incomplete investigation
- domain/tool misunderstanding

## Verify Difficulty

Run oracle:

```bash
harbor run -a oracle -p <task-folder>
```

Run real agents:

```bash
harbor run -a terminus-2 -m openai/@openai/gpt-5.2 -p <task-folder>
harbor run -a terminus-2 -m anthropic/@anthropic/claude-opus-4-6 -p <task-folder>
```

Record pass rates:

```text
GPT-5.2: ___ / 5 = ___%
Claude Opus 4.6: ___ / 5 = ___%
Worst-model accuracy: ___%
Best-model accuracy: ___%
Difficulty: hard / medium / easy
```

## Adjusting Difficulty

To make harder:

- add more meaningful steps
- use niche knowledge
- create debugging scenarios
- add realistic edge cases
- require verification of intermediate artifacts

## Revising Trivial Tasks

When a difficulty report says `trivial` or both frontier agents pass every run, treat the task as too locally patchable. Do not fix this by adding long instructions, more prose, or more copies of the same test.

First find why agents solved it easily:

- one obvious bug in one function
- tests only cover happy paths
- milestones only add aliases or dates to the same simple matcher
- the prompt points too directly at the edit
- no cross-row state, ranking, idempotency, config, or compatibility pressure

Raise difficulty through real behavior:

- add a new milestone with config-driven logic
- add candidate ranking and deterministic tie-breaks
- require row consumption or replay/idempotency
- preserve compatibility with older input schemas
- combine rules that can conflict, such as aliases plus date gates plus disabled config
- test every new requirement and update the oracle solution to compute it

A good revision for a trivial reconciliation task is something like: read an enabled-service policy from `/app/config/methods.csv`, support an `ANY` wildcard input value, select candidates by latest date, then configured priority, then source row order, and keep all previous schema/status/summary invariants. A weak revision is simply adding more aliases or making the prompt longer.

To make easier:

- reduce step count
- clarify requirements
- use more common technologies
- simplify the environment
- remove ambiguous edge cases

Do not make tasks easier by giving solution hints.
