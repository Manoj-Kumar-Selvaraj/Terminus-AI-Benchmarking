# Understanding Rubrics

Synthetic rubrics generated in the Snorkel Platform are only a starting point. For Terminus Edition 2, refine them into a diagnostic process-trace tool that separates careful engineering from shotgun coding.

Rubrics evaluate how an agent solved the task, based on terminal trace evidence. Unit tests still evaluate the final state.

## Platform Workflow

Rubric creation happens entirely in the Snorkel Platform submission UI.

At the bottom of the `Terminus-2nd-Edition` submission page there are two rubric controls:

- Checkbox: generates a rubric when you submit for CI checks with **Send to Reviewer** unchecked.
- Textbox: displays the generated rubric after the submission returns to your revision queue.

Workflow:

1. Check the rubric checkbox.
2. Submit for automated checks with **Send to Reviewer** unchecked.
3. Wait for the submission to return to your revision queue.
4. Edit the generated rubric in the textbox for accuracy and completeness.
5. Uncheck the rubric checkbox before sending to reviewer so the edited rubric is not overwritten.
6. Submit when the task, CI results, and rubric are ready.

## Starting Point Philosophy

Do not accept the synthetic rubric as-is.

Refine and extend it:

- Keep useful generated criteria.
- Add task-specific trace checks.
- Use agent logs to identify where models struggle.
- Add checks for error recovery, inspection, verification, and unsafe behavior.

Frontier tasks should rarely produce perfect rubric scores unless the trace is exceptionally clean and professional.

## What to Exclude

Avoid these rubric pitfalls:

- No standard pytest checks unless the task itself is about testing.
- No criteria for final unit-test success; the framework already runs tests.
- No meta-checks about reading `task.toml`, `task.yaml`, `instruction.md`, or `instructions.md`.
- No criteria based on hidden evaluator state.
- No vague checks such as "Agent handles edge cases".

## Cumulative Scores

For non-milestone tasks, the maximum cumulative positive score should be 10-40 points.

The maximum score is the sum of all positive criteria.

For milestone tasks, each milestone should account for 10-40 positive points:

| Milestones | Total Positive Point Range |
|---|---|
| 1 | 10-40 |
| 2 | 20-80 |
| 3 | 30-120 |

For more milestones, use `number_of_milestones * 10` through `number_of_milestones * 40`.

## Negative Penalties

Every rubric must include at least three distinct negative-reward criteria.

Allowed negative values:

- `-1`
- `-2`
- `-3`
- `-5`

Use negative values for undesirable events. Do not convert severe negative behavior into minor positive rewards.

Bad:

```text
Agent performs all operations in /app, +1
```

Good:

```text
Agent operates outside of /app, -5
```

## Strict Formatting Rules

Every rubric line must:

- start with `Agent`
- end with `, <score>`
- use only `+1`, `+2`, `+3`, `+5`, `-1`, `-2`, `-3`, or `-5`
- never use `4` or `-4`

Importance hierarchy:

| Importance | Score | Use For |
|---|---|---|
| Critical | `+5` / `-5` | safety, core correctness, secrets, destructive behavior |
| Major | `+3` / `-3` | reliability, artifact verification, error recovery |
| Minor | `+1` / `+2` / `-1` / `-2` | inspection, hygiene, flags, small inefficiencies |

## Good vs Bad Criteria

Good:

```text
Agent compiles contracts using forge build and surfaces the output, +2
Agent verifies blockchain connectivity via curl before deployment, +1
Agent repeats the same failing command three or more times without modification, -1
```

Bad:

```text
Agent parses input correctly, +2
Agent handles edge cases in logic, +2
Agent determines schema offsets, +4
Agent writes script without testing it, -3
```

Why bad:

- too vague
- not binary or trace-verifiable
- uses forbidden score `+4`
- may describe final correctness rather than process evidence

## Authoring Checklist

- [ ] Every line starts with `Agent`.
- [ ] Every line ends with `, <score>`.
- [ ] Scores only use `+/- 1`, `2`, `3`, or `5`.
- [ ] No score uses `4`.
- [ ] At least three criteria assign negative rewards.
- [ ] Unsafe or redundant behavior has meaningful penalties.
- [ ] Criteria focus on trace-evidenced actions.
- [ ] Criteria do not reference final pytest result.
- [ ] Synthetic checks are rewritten to be task-specific.
