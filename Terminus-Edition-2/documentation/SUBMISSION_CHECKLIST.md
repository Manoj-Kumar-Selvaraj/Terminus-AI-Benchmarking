# Terminus 2nd Edition Submission Checklist

Use this checklist before every submission. It is meant to catch issues before CI or peer review does.

For the detailed platform flow, see [PLATFORM_SUBMISSION_GUIDE.md](PLATFORM_SUBMISSION_GUIDE.md). For CLI submission, see [STB_CLI_GUIDE.md](STB_CLI_GUIDE.md).

## Pre-Submission Verification

### Task Design

- [ ] Problem statement is clear and unambiguous.
- [ ] All requirements are explicitly stated.
- [ ] Instructions use absolute paths, such as `/app/file.txt`.
- [ ] Output files are named in `instruction.md`.
- [ ] Data schemas and formats are fully specified.
- [ ] Difficulty target is less than 80% agent pass rate.
- [ ] Task is unique and not too similar to existing Edition 1 or Edition 2 tasks.
- [ ] Task is interesting and realistic, not just instruction-following.

### Diversity Requirements

- [ ] `codebase_size` is `small` or `large` for new submissions.
- [ ] Model difficulty is medium or hard.
- [ ] If the task is Python-heavy, model difficulty is hard.
- [ ] Milestones were considered if the task is naturally sequential.

## Required Files

Always required:

- [ ] `task.toml`: complete configuration with all required sections (see **Mandatory `task.toml` timeouts** below).
- [ ] `environment/Dockerfile`: builds successfully.
- [ ] Application dependencies are pinned to exact versions.
- [ ] Docker base image uses a specific version tag, not `latest`.

### Mandatory `task.toml` timeouts

Every task (milestone and non-milestone) must include:

```toml
[agent]
timeout_sec = 1800

[verifier]
timeout_sec = 900

[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"
```

Milestone tasks also need `[steps.agent]` / `[steps.verifier]` with `1800.0` / `900.0` on **each** `[[steps]]` block.

Ruby tasks: follow [RUBY_TASK_TEMPLATE.md](RUBY_TASK_TEMPLATE.md) and run `python3 scripts/normalize_ruby_tasks.py`.

- [ ] Top-level `[agent]` and `[verifier]` blocks present.
- [ ] `[environment]` matches the block above (`build_timeout_sec` may be `600.0` if justified).
- [ ] Every milestone step has `timeout_sec = 1800.0` (agent) and `900.0` (verifier).
- [ ] Repo-wide check: `python3 scripts/audit_fix_task_toml_timeouts.py --dry-run` reports zero issues.
- [ ] Repo-wide common-issue scan: `python3 scripts/audit_all_tasks_common_issues.py` (use `--fix` for auto-fixes, `--preflight` to include structural preflight).

### Non-Milestone Tasks

Use when `number_of_milestones = 0`.

- [ ] `instruction.md`: clear, concise, human-written instructions.
- [ ] `solution/solve.sh`: deterministic, human-written oracle solution.
- [ ] `tests/test.sh`: uses the required test runner pattern and produces `/logs/verifier/reward.txt`.
- [ ] `tests/test_outputs.py`: pytest tests with docstrings that verify behavior.
- [ ] `environment/Dockerfile`: does not copy `solution/` or `tests/` into the image.

### Milestone Tasks

Use when `number_of_milestones >= 2`.

- [ ] `task.toml` includes one `[[steps]]` block per milestone.
- [ ] `number_of_milestones` equals the number of `[[steps]]` blocks.
- [ ] No root-level `instruction.md`.
- [ ] No root-level `tests/`.
- [ ] No root-level `solution/`.
- [ ] No root-level `milestone_x.md`.

For each milestone `N`:

- [ ] `steps/milestone_N/instruction.md`: prompt for milestone `N` only.
- [ ] Milestone 1 includes the overall task context.
- [ ] `steps/milestone_N/tests/test.sh`: milestone `N` test runner.
- [ ] `steps/milestone_N/tests/test_mN.py`: pytest assertions scored only against milestone `N`.
- [ ] `steps/milestone_N/solution/solve.sh`: wrapper that runs `solveN.sh`.
- [ ] `steps/milestone_N/solution/solveN.sh`: oracle solution scoped only to milestone `N`.

## Rubric

Every submission should include a rubric aligned to the task. **Whenever you change instructions, tests, or solutions, update every rubric copy in the same edit session** — do not zip until they match.

- [ ] Reviewed [RUBRICS_GUIDE.md](RUBRICS_GUIDE.md).
- [ ] Generate the synthetic rubric through the Snorkel Platform submission UI.
- [ ] Edit the rubric for accuracy and completeness.
- [ ] Include at least three criteria with negative rewards, such as `-1`.
- [ ] Rubric criteria are objective and binary.
- [ ] Rubric criteria can be judged from terminal trace evidence.
- [ ] Rubric does not reference tests, oracle, NOP, `task.toml`, or `instruction.md`.
- [ ] Scores use only `+1`, `+2`, `+3`, `+5` and `-1`, `-2`, `-3`, `-5`.
- [ ] Synced all local rubric locations for this task (same text in each):
  - `<task>/rubric.txt`
  - `ALL_RUBRICS_20260526/parser_safe/<task>_rubric.txt`
  - `ALL_RUBRICS_20260526/milestone_blocks/<task>_rubric_1.txt` … `_3.txt` (milestone tasks)
  - `ALL_RUBRICS_STRICT_20260526/copy_paste/<task>_rubric.txt`
  - `ALL_RUBRICS_STRICT_20260526/milestone_blocks/<task>_rubric_1.txt` … `_3.txt` (milestone tasks)

## Quality Standards

- [ ] All requirements have corresponding tests.
- [ ] Tests cover explicit requirements.
- [ ] Tests cover implicit expected behavior.
- [ ] Tests cover critical edge cases.
- [ ] Anti-cheating measures are in place.
- [ ] No hints or exposed answers are present in the environment.
- [ ] Tests check behavior, not implementation, unless implementation evidence is truly part of the task.
- [ ] Task complies with Edition 2 quality guidelines.

## Automated Checks

### Oracle Agent

Run:

```bash
harbor run -a oracle -p <task-folder>
```

Result:

- [ ] Oracle agent passes.

### CI Checks

Run:

```bash
harbor tasks check <task-folder> -m openai/@openai/gpt-5.2
```

Expected checks:

- [ ] `pinned_dependencies`
- [ ] `typos`
- [ ] `tests_or_solution_in_image`
- [ ] `test_deps_in_image`
- [ ] `check_canary`
- [ ] `check_dockerfile_references`
- [ ] `check_test_sh`
- [ ] `check_task_absolute_path`
- [ ] `check_privileged_containers`
- [ ] `ruff`
- [ ] `check_task_sizes`
- [ ] `validate_task_fields`

### LLMaJ Checks

Expected checks:

- [ ] `behavior_in_task_description`
- [ ] `behavior_in_tests`
- [ ] `informative_test_docstrings`
- [ ] `anti_cheating_measures`
- [ ] `structured_data_schema`
- [ ] `hardcoded_solution`
- [ ] `file_reference_mentioned`

## Real Agent Testing

Run GPT-5.2:

```bash
harbor run -a terminus-2 -m openai/@openai/gpt-5.2 -p <task-folder>
```

Record:

- [ ] Run 1: PASS / FAIL
- [ ] Run 2: PASS / FAIL
- [ ] Run 3: PASS / FAIL

Run Claude Opus 4.6:

```bash
harbor run -a terminus-2 -m anthropic/@anthropic/claude-opus-4-6 -p <task-folder>
```

Record:

- [ ] Run 1: PASS / FAIL
- [ ] Run 2: PASS / FAIL
- [ ] Run 3: PASS / FAIL

## Difficulty Calculation

| Difficulty | Accuracy Target | Description |
|---|---|---|
| Hard | Accuracy <= 20% on the best model, or <= 20% on the worst model | Requires deep expertise and multi-step reasoning |
| Medium | 20% < accuracy <= 60% on the worst model | Moderate complexity and some domain knowledge |
| Easy | 60% < accuracy <= 80% on the worst model | Straightforward but still non-trivial |

Record:

```text
Worst-model pass rate: ____%
Best-model pass rate: ____%
Difficulty: Easy / Medium / Hard
```

Tasks where the worst model scores above 80% will not be accepted.

## Final Review

Use the reviewer checklist before submitting. Validate the task against the same criteria reviewers use.

Helpful references:

- [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md)
- [COMMON_ERRORS.md](COMMON_ERRORS.md)
- [REVIEWER_CHECKLIST.md](REVIEWER_CHECKLIST.md)

Self-check questions:

- [ ] Would I understand this task as a first-time reader?
- [ ] Are there any ambiguous requirements?
- [ ] Could an agent cheat on this task?
- [ ] Do tests verify actual behavior?
- [ ] Is the solution deterministic?
- [ ] Does every important requirement have test coverage?
- [ ] Does the rubric match the current task?

If the answer reveals a problem, fix it before submitting.

## Submission Method

- [ ] Created ZIP of files, not the containing folder.
- [ ] All required files are included in the ZIP.
- [ ] Uploaded to `Terminus-2nd-Edition` on the Snorkel Expert Platform, or submitted through `stb`.
- [ ] Metadata is complete.
- [ ] Rubric checkbox is selected when submitting through the platform.
- [ ] **Send to reviewer** stays unchecked until CI and rubric are reviewed.

## After Submission

### Review Timeline

| Stage | Typical Time |
|---|---|
| Automated CI checks | Immediate |
| Peer review assignment | 1 day |
| Initial review | 1-3 business days |
| Follow-up reviews | 1-2 business days |
| Total | 3-7 business days |

### Review Process

Immediately after submission:

- CI checks run.
- LLMaJ checks run.
- Oracle agent runs.

During peer review, a qualified coding expert reviews:

- task clarity and correctness
- solution validity
- test coverage
- anti-cheating measures
- overall quality

Agent evaluation runs the task against:

- GPT-5.2 with Codex agent, 5 runs
- Claude Opus 4.6 with Claude Code, 5 runs

The pass rate determines the final difficulty classification.

## Review Outcomes

### Approved

The task is accepted.

- Task is added to the benchmark suite.
- Credit is recorded in your profile.

### Changes Requested

The reviewer found issues that need fixing.

What to do:

- Read feedback carefully.
- Understand each requested change.
- Make targeted fixes locally.
- Re-run all checks.
- Resubmit or push updates.

### Declined

The task does not meet criteria.

Common reasons:

- too easy
- unclear requirements
- too similar to an existing task
- fundamental design issues

What to do:

- Review the feedback.
- Decide whether the task can be salvaged.
- Significantly revise or start fresh.
- Appeal if you disagree.

## Addressing Feedback

Read carefully:

- Is it a minor fix or major revision?
- Did the reviewer explain the reasoning?
- Are specific lines or files mentioned?

Make targeted changes:

- Do not rewrite everything unless the feedback requires it.
- Fix only what is needed.
- Use the reviewer checklist to cover all high-severity and relevant medium-severity criteria before resubmitting.

Explain changes:

- On the platform, add a revision summary note.
- If using the CLI, include clear notes with the update or review response flow.

Re-request review:

- Update the submission status after pushing changes.

If you disagree:

- Respond politely with reasoning.
- Provide evidence for your approach.
- Be open to compromise.
- Escalate to Slack if needed.

Reviewers are trying to help; most disagreements are resolved through discussion.

## Faster Acceptance Tips

- Run all checks locally before submitting.
- Follow this checklist exactly.
- Write clear, concise `instruction.md`.
- Address feedback promptly.
- Ask questions if feedback is unclear.
