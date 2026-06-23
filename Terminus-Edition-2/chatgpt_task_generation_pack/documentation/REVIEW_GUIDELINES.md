# Review Guidelines

Reviewers protect benchmark quality. A good review is comprehensive, clear, and actionable.

Do not stop after finding the first issue. Identify all meaningful issues in one pass so the contributor can fix everything without repeated drip feedback.

## Review Philosophy

As a reviewer, your goals are to:

- catch issues before they enter the dataset
- help contributors improve tasks
- maintain consistency across submissions
- distinguish task difficulty from task unfairness

Feedback should explain:

- what is wrong
- where it appears
- why it matters
- how to fix it

## Review Flow

### 1. Read the Task Description

Check the six prompt principles:

- concise
- well specified
- interesting
- no answers or hints
- unique
- absolute paths

### 2. Review Tests

Check:

- every requirement has a corresponding test
- tests have informative docstrings
- tests verify behavior, not implementation
- no brittle string matching
- no unreasonable hardcoded thresholds
- no order dependency

### 3. Use Test-Quality Eval

Treat automated test-quality flags as helpers, not replacements for review.

Flags:

| Flag | Meaning |
|---|---|
| `req-gap` | instruction requires behavior no test asserts |
| `weak-assertion` | test too loose to catch wrong solutions |
| `phantom-spec` | tests enforce behavior not described |
| `flaky-execution` | correct solution can fail due to infra/timing |
| `vacuous-test` | test can pass regardless of output |

### 4. Check Solution

Verify:

- solution demonstrates process
- commands are deterministic
- works in provided environment
- matches instructions
- not hardcoded to tests

### 5. Verify Metadata

Check:

- difficulty matches observed pass rate
- category/subcategories fit
- tags/languages are accurate
- time estimates are realistic
- timeouts are sufficient but not excessive

### 6. Watch Agent Runs

Passing a run means one run passes every unit test.

Solvable means that across runs, every individual test passes at least once, even if no single run passes all tests.

When agents fail, decide whether failure is good or bad:

- good: reasoning error, missed edge case, domain/tool gap
- bad: ambiguity, missing information, environment issue, unfair tests

## Common Issues to Flag

Instructions:

- ambiguous language
- missing output specs
- relative paths
- implicit assumptions
- unverifiable tool requirements

Tests:

- brittle string matching
- missing coverage
- order dependency
- implementation testing
- too many tests for a simple task

Solutions:

- hardcoded answers
- nondeterminism
- incomplete steps
- unnecessary complexity

Cheating:

- exposed test logic
- answer in git history
- mutable data files
- decompilable hidden answers
- dummy program replacement

## Review Actions

### Approve

Use when the task is ready and no blocking issues remain.

### Request Changes

Use when fixable issues need revision.

Good feedback:

```text
The test test_output_format uses exact string matching. Please change it to check for required fields while allowing valid formatting differences.
```

Bad feedback:

```text
Tests need work.
```

### Decline

Use for fundamental issues:

- too easy
- duplicate task
- flawed core concept
- impossible/unfair requirements

Explain whether a major revision could salvage it.
