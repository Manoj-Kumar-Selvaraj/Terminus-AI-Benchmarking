# Terminus 2nd Edition FAQ

Last source update represented here: April 27, 2026.

## Getting Started

### How do I get started?

Review the project docs, read pinned posts in `#terminus-2nd-edition-submission` and `#terminus-2nd-edition-announcements`, then complete the assessment on the Snorkel dashboard.

### Where is the assessment?

On your dashboard under `Terminus-2nd-Edition-Assessment`. If you do not see it, ask in Slack.

### Should I wait for my first task to be reviewed before starting another?

No. You can work on multiple tasks in parallel.

### How do I initialize a task with CLI?

```bash
stb init my-task-name -p "terminus-2nd-edition" -t base
```

## CLI and API Keys

### My account is not assigned to any Terminal-Bench project.

Complete and pass onboarding first, then wait for assignment confirmation.

### I hit the key refresh limit.

Ask an admin in Slack to reset or replenish your key.

### How do I get an API key for agent testing?

Use the CLI:

```bash
stb keys refresh
```

## Milestones and File Layout

### What does a milestone task require?

For N milestones:

- `task.toml` with N `[[steps]]` blocks
- `environment/Dockerfile`
- `steps/milestone_N/instruction.md`
- `steps/milestone_N/tests/test.sh`
- `steps/milestone_N/tests/test_mN.py`
- `steps/milestone_N/solution/solve.sh`
- `steps/milestone_N/solution/solveN.sh`

No root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md`.

### What should `number_of_milestones` be for non-milestone tasks?

`0`.

Setting it to `1` for a non-milestone task is incorrect.

## Difficulty, Language, and Codebase Size

### What are difficulty requirements?

- Python tasks must be hard.
- Non-Python tasks must be medium or hard.
- Trivial tasks are blocked.

### What is hard?

Hard means accuracy is <= 20% on either the best model or worst model across GPT-5.2 and Claude Opus 4.6.

### How is `codebase_size` determined?

By files in `environment/`, excluding Dockerfile and compose:

- `minimal`: 0-19, not accepted for new submissions
- `small`: 20+
- `large`: 200+

Use lowercase values.

### My non-Python task is flagged as Python.

If `languages` includes Python anywhere, it may be treated as Python. Remove Python if it is only used for test infrastructure and not the task language.

## Testing and Docker

### Solvable vs passing a run?

Passing a run means one agent run passes all unit tests.

Solvable means that across multiple runs, each individual unit test passes at least once.

### Correct model strings?

Use:

```text
@openai/gpt-5.2
@anthropic/claude-opus-4-6
```

### reward.txt not found on platform.

Common causes:

- blocking entrypoint prevents `test.sh`
- `set -euo pipefail` exits before reward
- missing `/logs/verifier` directory

Use a test runner that writes reward even on failure.

### Environment files not found by Docker.

Harbor build context is `environment/`. Move everything Docker needs into `environment/`.

### Docker network errors after many tests.

Run:

```bash
docker network prune
```

## Submissions and Reviews

### How do I check submission status?

```bash
stb submissions list -p PROJECT_ID
stb submissions list -p PROJECT_ID --show-folder-names
```

Details:

```bash
stb submissions view SUBMISSION_ID
stb submissions feedback SUBMISSION_ID
stb submissions download SUBMISSION_ID
```

### Status meanings

| Status | Meaning | Can Update? |
|---|---|---|
| `EVALUATION_PENDING` | automated checks running | No |
| `NEEDS_REVISION` | reviewer requested changes | Yes |
| `REVIEW_PENDING` | waiting for reviewer | No |
| `ACCEPTED` | accepted | No |
| `OFFERED` | offer made | No |
| `REJECTED` | rejected | No |
| `SKIPPED` | skipped | No |

### Daily submission limits

- New contributors: 2 new submissions per day.
- Established contributors with 2+ accepted tasks: 5 new submissions per day.
- Revisions do not count.

## Rubrics and Quality Checks

### Rubric requirements?

- At least one negative criterion per milestone rubric.
- Total positive points should be 10-40 per milestone.
- Generate and edit rubrics through the platform UI.

### Rubrics disappeared after revision.

Known platform issue. Report with task UUID in Slack.

## Support

Use:

- `#terminus-2nd-edition-submission`: general questions, tech issues, submission help.
- `#terminus-2nd-edition-announcements`: guideline updates.

Office hours are posted in announcements.

## Known Issues

- AutoEval may fail intermittently; resubmit or report IDs.
- Reviewer feedback may reference stale/wrong task files; dispute with screenshots.
- New guidelines should not be enforced on older revisions.
- Non-Python tasks can be flagged as Python if `languages` includes Python.
- `source "$HOME/.local/bin/env"` may be false-flagged as typo.
