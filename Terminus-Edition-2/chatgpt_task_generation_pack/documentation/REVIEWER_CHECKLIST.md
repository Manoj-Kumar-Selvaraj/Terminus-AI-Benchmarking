# Terminal Bench Edition 2 Reviewer Checklist

This checklist summarizes review criteria and severity levels for Terminus Edition 2 tasks.

## Severity Guidance

High: if any high-severity criterion fails, the task should not be accepted.

Medium: multiple medium failures should block acceptance. A single medium failure can be accepted with a note.

Low: nice-to-have. Low-only issues do not block acceptance, but include them if requesting revisions for other reasons.

## Instruction Prompt

High:

- Task instruction is concise.
- Task instruction is well specified.
- Task instruction is interesting.
- Task instruction does not provide hints or solution strategy.
- Task is unique relative to TB2, TB3, and Terminus Edition 1.
- Instruction uses absolute paths.

Medium:

- `instruction.md` does not contain a canary string.
- `instruction.md` does not contain the task name as boilerplate.

## Environment

High:

- Dockerfile/build scripts do not fetch content from the web except packages.
- Language/package dependencies use pinned versions.
- Build context does not use files outside `environment/`.
- Environment does not contain solution or ground truth.
- Dockerfile does not require dangerous operations.
- Compose does not conflict with Harbor reserved mounts.

Low:

- Apt packages pinned where useful.
- Base image uses specific version tag.
- Dockerfile avoids heredocs.

## Oracle Solution

High:

- Oracle passes consistently.
- Oracle does not use internet or download packages.
- Oracle solves the task described in `instruction.md`.
- Oracle is an implementation, not a hardcoded answer.

## Verifiers

High:

- Verifier cannot exit before reward is assigned.
- Same verifier logic for oracle and agent.
- Verifier only downloads pinned dependencies if needed.
- Verifier applies binary reward only.
- Verifiers align with instructions.
- Verifiers check correctness, not just format.

## Rubrics

High:

- Rubric does not reference testing logic.
- Rubric does not reference metadata or `instruction.md`.
- Rubric has at least three negative criteria.
- Scores are only `+/-1`, `+/-2`, `+/-3`, `+/-5`.
- Each line starts with `Agent` and ends with `, <score>`.
- Criteria are detailed and precise.

Medium:

- Each milestone rubric has at least one negative criterion.
- Scores map to importance.
- Negative behavior is phrased as factual action with negative score.
- Rubric does not mention oracle or NOP.

Low:

- Point range is 10-40 positive points per milestone.

## Task Structure

High:

- Non-milestone tasks contain `instruction.md`, `task.toml`, `environment/`, `solution/solve.sh`, `tests/test.sh`, and `tests/test_outputs.py`.
- Milestone tasks contain `task.toml`, `environment/`, and one `steps/milestone_N/` per milestone.
- Milestone directories contain per-milestone instruction, tests, and solution files.
- Milestone tasks do not use root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md`.

Low:

- Parent directory has no unnecessary files such as job logs, caches, or stray data.

## Task Metadata

High:

- `task.toml` has all required metadata fields.
- Non-milestone tasks have `[agent]` and `[verifier]`.
- Milestone tasks have one `[[steps]]` block per milestone with per-step agent/verifier timeouts.
- `[environment]` has build timeout, CPU, memory, and storage limits.
- Compose tasks set `custom_docker_compose = true`.
- Multi-container tasks set `is_multi_container = true`.

Medium:

- Tags, languages, categories, and subcategories fit the task.

## Milestone Tasks

High:

- Milestone tasks have at least two milestones.
- Milestone tasks use `steps/milestone_N/`.
- `task.toml` declares one `[[steps]]` block per milestone.
- Each milestone has `solveN.sh`.
- Each milestone has `test_mN.py` with `TestMilestoneN`.
- Tests score only that milestone.

Medium:

- Per-milestone instructions cover only that milestone, with overall context in milestone 1.
