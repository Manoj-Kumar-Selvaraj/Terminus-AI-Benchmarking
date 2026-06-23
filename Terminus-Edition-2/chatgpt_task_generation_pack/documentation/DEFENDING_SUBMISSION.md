# Defending Your Submission

Use this guide when responding to review feedback, revision requests, or declines.

## Read Feedback Carefully

Before responding:

- read each comment fully
- understand what is being asked
- decide if the feedback is valid
- check whether you missed something

## Acknowledge Valid Points

If the reviewer is right, say so clearly:

```text
You're right, the test on line 45 uses brittle string matching. I updated it to check for required fields instead.
```

## Explain Your Reasoning

If you disagree or need clarification, explain calmly:

```text
I chose exact string matching here because the output format is strictly specified in the instructions. Would checking for the required fields be preferred, or should I clarify the exact-output requirement?
```

## Ask Questions

If feedback is unclear:

```text
Could you clarify what you mean by "tests are too strict"? Are you referring to format checking or value validation?
```

## Making Changes

Be thorough:

- address every point
- do not skip comments
- re-run checks after changes

Be explicit:

```text
Addressed review feedback:
- Line 45: changed exact string match to field check.
- Line 67: added docstring to test_output.
- instruction.md: clarified output format.
```

Do not over-engineer. Fix what is asked unless the task has a broader design flaw.

## When to Push Back

It is okay to disagree if:

- you have a valid technical reason
- the feedback misunderstands the approach
- the requested change would break the task

Bad:

```text
That's wrong. My approach is fine.
```

Good:

```text
I understand the concern about brittleness, but in this case the exact format is the user-facing requirement and is specified in the prompt. I can add a note clarifying that exact output is required.
```

## Escalation

If disagreement cannot be resolved:

1. Document your position clearly in the submission.
2. Use the portal dispute mechanism if available.
3. Escalate in Slack with task/submission IDs and evidence.

## Appeal Template

```text
I'd like to appeal this decision.

Reviewer said: [quote feedback]

My response: [explanation]

Evidence: [specific files, lines, run outputs, docs]

I believe this task should be reconsidered because [reason].
```

## Tips

- Run all checks locally before submitting.
- Self-review before upload.
- Respond within 1-2 days when possible.
- Be collaborative, not defensive.
- If declined, decide whether to salvage or start fresh.
