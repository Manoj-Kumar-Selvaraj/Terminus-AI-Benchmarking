# Bad Example Tasks

Use these anti-examples to avoid common task-quality failures.

## Too Easy

Bad prompt:

```markdown
Write a function that reverses a string.
```

Problem: one-liner in most languages; agents solve instantly.

## Too Vague

Bad prompt:

```markdown
Build a web scraper.
```

Problem: no specific requirements and impossible to verify reliably.

## Requires External Resources

Bad prompt:

```markdown
Query the Twitter API to get trending topics.
```

Problem: requires API credentials and network access.

## Ambiguous Success Criteria

Bad prompt:

```markdown
Make this code better.
```

Problem: "better" is subjective without specific metrics.

## Task Inspiration

Better directions:

- concurrency bugs: race conditions, deadlocks
- algorithms with specific constraints
- refactoring with measurable behavior preservation
- security vulnerability discovery and repair
- performance optimization with stable benchmarks
- realistic API, DB, or tool-specific debugging
