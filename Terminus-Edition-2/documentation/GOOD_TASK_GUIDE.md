# What Makes a Good Task

A good Terminus Edition 2 task is one an expert human can solve confidently, but that challenges or stumps current AI coding agents.

Good tasks are not trivia, trick questions, or simple script completion. They require multi-step reasoning, domain expertise, and practical problem solving in a realistic environment.

## Core Principle

Make the task hard because the engineering work is real, not because the prompt is vague or overloaded.

The agent should need to inspect, reason, modify, and verify.

## Key Requirements

### Difficulty Target

The worst-performing model's accuracy across GPT-5.2 and Claude Opus 4.6 must be <= 80%.

| Difficulty | Accuracy Target | Description |
|---|---|---|
| Hard | Accuracy <= 20% on the best model, or <= 20% on the worst model | Deep expertise and multi-step reasoning |
| Medium | 20% < accuracy <= 60% on the worst model | Moderate complexity and some domain knowledge |
| Easy | 60% < accuracy <= 80% on the worst model | Straightforward but non-trivial |

Current diversity policy accepts only medium and hard model-difficulty tasks for new submissions. Easy tasks are blocked.

### Multi-Step Complexity

Tasks must require chaining multiple commands, handling intermediate state, and reasoning.

Good:

```text
Debug the failing test suite, fix the three bugs causing failures, and verify all tests pass.
```

Bad:

```text
Run the test suite.
```

Single-command tasks are too easy.

### Clear and Unambiguous

The task must be fully specified. The agent should understand what success means without guessing.

Good:

```text
Implement /app/search.py so find_longest_palindrome(s: str) returns the longest palindromic substring. If there are ties, return the first one.
```

Bad:

```text
Write code for palindromes.
```

### Testable and Verifiable

Every task needs deterministic tests that verify completion.

```python
def test_longest_palindrome():
    """Verify longest palindrome behavior on representative edge cases."""
    assert find_longest_palindrome("babad") in ["bab", "aba"]
    assert find_longest_palindrome("cbbd") == "bb"
    assert find_longest_palindrome("") == ""
```

### No Cheating Opportunities

Think like a shortcut-seeking agent. Ensure the task cannot be passed by:

- reading test files for answers
- editing data files to match expected output
- deleting tests
- hardcoding expected outputs
- replacing real programs with dummy scripts
- copying solution or ground-truth files from the environment

## How to Make Tasks Harder

- Debugging tasks: require root-cause analysis.
- Niche knowledge: use public but less common domains, tools, or formats.
- Bespoke rules: mix custom rules with familiar ones, while keeping them specified.
- Multi-step tasks: require several meaningful actions with verification.
- Milestones: structure larger tasks into sequential validated stages.

## What to Avoid

| Avoid | Why |
|---|---|
| Trivia questions | Tests memorization, not engineering |
| Ambiguous requirements | Agents cannot know what is expected |
| External dependencies | API keys, live network, or flaky services break reproducibility |
| Simple one-liners | Agents solve instantly |
| Brittle tests | Exact string matching and hardcoded values reject valid solutions |
| Huge prompt specs | Tests instruction following more than engineering |

## Quality Checklist

- [ ] Problem statement is clear and complete.
- [ ] Difficulty is medium or hard by model pass rate.
- [ ] Multi-step reasoning is required.
- [ ] All constraints are explicitly stated.
- [ ] Test cases cover all requirements.
- [ ] No cheating opportunities are exposed.
- [ ] `instruction.md` is human-written and not LLM-styled.
- [ ] Task is unique relative to existing Terminus tasks.
