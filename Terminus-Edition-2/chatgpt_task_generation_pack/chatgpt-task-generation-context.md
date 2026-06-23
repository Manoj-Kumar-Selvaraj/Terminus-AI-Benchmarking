# ChatGPT Context for Terminus Edition 2 / Terminal-Bench 3.0 Task Generation

Use this context when asking ChatGPT to create a new Terminus Edition 2 / Terminal-Bench 3.0 task. Attach the companion documentation ZIP and, when useful, a small number of similar reference tasks. References are for structure, conventions, and quality expectations only. Do not clone their task design.

## Copy/Paste Prompt

Create a new Terminus Edition 2 / Terminal-Bench 3.0 task.

Task idea: `<TASK_IDEA_OR_NAME>`

I am attaching the repository documentation/reference ZIP and possibly similar reference tasks. Use the references only for structure and conventions, not for cloning the task design.

Your output must include:

- a complete task folder
- a task ZIP
- an external rubric
- a validation report
- a short summary of the milestone arc, verifier coverage, oracle behavior, and any limitations

## Core Design Requirements

1. Create a genuinely distinct hard task.
2. Avoid CSV matcher/reconciler patterns unless I explicitly request one.
3. Avoid repeated milestone arcs such as alias normalization -> calendar/date window -> audit/report.
4. Prefer a production incident or stateful business-processing narrative where the user sees symptoms first.
5. Use a system-oriented title, not a root-cause title.
6. Agent-facing instructions must be symptom-first and sufficient.
7. Do not disclose hidden fixes, exact implementation primitives, or oracle shortcuts in agent-facing text.
8. Build cumulative milestones where each fix reveals the next failure.
9. Add at least two evidence artifacts, such as logs, traces, control files, terminal captures, queue dumps, stack traces, profiles, state snapshots, runbooks, or incident notes.
10. Verifier tests must check behavior and system state, not just exact strings.
11. Include negative cases, edge cases, malformed input, missing state, retry/idempotency behavior, and boundary cases appropriate to the domain.
12. Confirm earlier milestone solutions do not pass later milestone tests.
13. Keep the oracle implementation aligned with the instructions and tests.
14. Do not solve by replacing the whole application with a bypass unless the task explicitly allows that style.
15. Add compatibility constraints that prevent wholesale rewrites, such as preserving public CLI flags, HTTP routes, file formats, database schemas, lock files, queue message contracts, or exported function names.
16. Produce a clean ZIP and an external rubric. The rubric is not included in the task ZIP unless the local repository convention specifically says otherwise.
17. Run local compile, preflight, tests, oracle, and packaging validation as much as possible.

## Edition 2 Layout Expectations

For milestone tasks, use this structure:

```text
your-task-name/
  task.toml
  environment/
    Dockerfile
    ...
  steps/
    milestone_1/
      instruction.md
      tests/
        test.sh
        test_m1.py
      solution/
        solve.sh
        solve1.sh
    milestone_2/
      instruction.md
      tests/
        test.sh
        test_m2.py
      solution/
        solve.sh
        solve2.sh
```

Milestone tasks should not include root-level `instruction.md`, root-level `tests/`, root-level `solution/`, or `milestone_x.md`.

`task.toml` must use `version = "2.0"`, complete `[metadata]`, `[environment]`, and one `[[steps]]` block per milestone. Include timeouts for every step:

```toml
[steps.agent]
timeout_sec = 1800.0

[steps.verifier]
timeout_sec = 900.0
```

Many local tasks also include top-level `[agent]` and `[verifier]` blocks for reviewer compatibility:

```toml
[agent]
timeout_sec = 1800.0

[verifier]
timeout_sec = 900.0
```

Use `/app` as the working directory and absolute paths in instructions and tests.

## Instruction Quality

Instructions should read like an operator report, customer incident, or production handoff. They should describe symptoms, affected artifacts, constraints, and expected user-visible behavior. They should not say "fix the off-by-one in parser.go" or reveal exact hidden gates.

Good instructions include:

- what command or workflow is failing
- where evidence lives under `/app`
- what compatibility must be preserved
- what outputs or runtime behavior must be correct
- what must not be changed
- how success will be observed at a high level

Bad instructions include:

- the hidden root cause
- names of private test cases
- implementation recipes that make the task mechanical
- vague goals such as "make it work" without artifacts or contracts

## Milestone Design

Each milestone must be a prerequisite for the next. Milestone 1 should establish the main incident and restore a narrow capability. Later milestones should reveal deeper failures only after the earlier repair is in place.

Prefer arcs like:

- service starts but loses in-flight state under restart
- replay fixes restart but breaks idempotency under duplicate delivery
- idempotency fixes duplicates but exposes concurrency or lease expiry
- concurrency fixes steady state but must preserve backwards-compatible telemetry, CLI, or migration behavior

Avoid arcs like:

- add aliases
- add calendar/date logic
- add report summary

Each milestone verifier should score only that milestone while tolerating state left by prior milestones. Later verifier fixtures should include cases that a prior milestone-only solution cannot pass.

## Test Quality

Tests should be deterministic, behavior-oriented, and aligned with explicit instructions. Every important requirement should have direct verifier coverage.

For each milestone:

- use a single `TestMilestoneN` class in `test_mN.py`
- give every test an informative docstring
- build/run the real application workflow, not a mocked bypass
- assert behavior, persisted state, side effects, and compatibility contracts
- include negative and malformed cases
- include at least one edge case that catches naive or shortcut implementations
- assert that old legacy outputs are absent when paths change
- avoid brittle checks for exact log text unless the output contract requires it

`test.sh` must run pytest and write `/logs/verifier/reward.txt`. Keep dependencies pinned.

## Oracle Expectations

Oracle solutions should be deterministic, idempotent when practical, and scoped to the milestone. They should repair the application or configuration in a realistic way, not simply write expected output files.

For milestone tasks:

- `solve.sh` should be a thin wrapper that uses `SCRIPT_DIR`
- `solveN.sh` should contain the milestone N repair
- avoid wrappers that depend on absolute local repository paths
- ensure oracle scripts are present in the current milestone's mounted solution directory
- keep hidden oracle code out of the Docker image

If an oracle embeds substantial source code, prefer separate source files copied by the solve script when that matches the local convention.

## Rubric Requirements

Create an external rubric that evaluates the agent's process trace, not just final test success. Rubric lines should start with `Agent`, end with a score, and use only `+1`, `+2`, `+3`, `+5`, `-1`, `-2`, `-3`, or `-5`.

Good rubric criteria cover:

- inspecting evidence artifacts before editing
- identifying the correct subsystem boundary
- preserving compatibility constraints
- using targeted fixes instead of rewrites
- adding or running focused verification
- handling restart, retries, ordering, malformed state, or concurrency safely

Include at least three negative criteria for unsafe behavior, bypasses, hardcoding, destructive commands, or ignoring evidence.

Do not include rubric points for simply reading `instruction.md` or passing pytest.

## Validation Requirements

Before finalizing, run as much local validation as possible:

```bash
bash scripts/terminus2_cli.sh preflight ./your-task-name
bash scripts/terminus2_cli.sh oracle ./your-task-name
bash scripts/zip.sh your-task-name
```

Also inspect the final ZIP listing to confirm it excludes unintended files such as `.git`, logs, generated caches, local oracle logs, old task ZIPs, and unrelated artifacts.

The validation report should include:

- commands run
- pass/fail status
- test counts per milestone
- known limitations
- final task ZIP path
- external rubric path

## Go Task Guidance

For Go tasks, prefer realistic system behavior over data matching:

- HTTP/TLS failure recovery
- deterministic concurrency
- context cancellation and deadlines
- retry, lease, checkpoint, or queue semantics
- file descriptor, socket, or goroutine leak prevention
- stable CLI/API compatibility
- `go test -race` where useful and deterministic

Do not make a Go task that can be solved by replacing the whole binary with a small script or by hardcoding output files.

## COBOL / PL/I Task Guidance

For COBOL and PL/I tasks, prefer mainframe-flavored operational behavior:

- fixed-width records
- copybook/layout drift
- control totals
- ABEND restart
- committed ledgers
- checkpoint files
- SQLCODE simulation
- sort/merge behavior
- file-status handling
- trailer/header validation

Avoid making the task a simple CSV-like reconciliation. Use records, offsets, sequence numbers, restart markers, and operator reports to create realistic debugging work.

## CICS Task Guidance

For CICS-style tasks:

- use GnuCOBOL application code plus a trusted Go CICS simulator
- do not require real IBM CICS or z/OS
- test pseudo-conversation behavior, COMMAREA, TSQ/TDQ, record locking, syncpoint, rollback, and terminal continuation
- include terminal captures and state snapshots as evidence artifacts
- preserve transaction IDs, map names, and message formats as compatibility constraints

## Self-Audit Before Returning

Before returning the task, answer these checks explicitly:

- Is the task distinct from the references?
- Is it not a CSV matcher/reconciler?
- Does each milestone reveal a new failure only after prior repairs?
- Are at least two evidence artifacts present?
- Do instructions avoid disclosing hidden fixes?
- Do tests check behavior, not implementation strings?
- Are negative and edge cases covered?
- Can an earlier milestone solution pass later milestone tests? If yes, fix the tests or milestone arc.
- Does the oracle implement the same behavior that instructions require?
- Is wholesale replacement prevented by compatibility constraints?
- Is the final ZIP clean?
- Is the rubric external and aligned with the milestone arc?

