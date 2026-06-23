# Agent Review Reference

Agent Review uses Claude Code to statically evaluate Terminal-Bench tasks for format compliance, best practices, and quality issues.

Agent Review currently does not block submission. Treat it as an additional tool for finding warnings, potential issues, and improvement areas.

## How It Works

Agent Review reads task files without executing code or building containers.

It produces a structured report with:

- task summary
- issues by severity
- actionable fix recommendations
- overall recommendation

## What Gets Reviewed

### File Structure

Non-milestone tasks:

- `environment/Dockerfile`
- `instruction.md`
- `task.toml`
- `solution/solve.sh`
- `tests/test.sh`
- `tests/test_outputs.py`

Milestone tasks:

- `environment/Dockerfile`
- `task.toml` with one `[[steps]]` block per milestone
- `steps/milestone_N/instruction.md`
- `steps/milestone_N/tests/test.sh`
- `steps/milestone_N/tests/test_mN.py`
- `steps/milestone_N/solution/solve.sh`
- `steps/milestone_N/solution/solveN.sh`

Multi-container tasks:

- `environment/docker-compose.yaml`
- required flags in `task.toml`
- service Dockerfiles if present

### task.toml

Checks:

- `version = "2.0"`
- required author fields
- valid difficulty
- valid category and subcategories
- valid `codebase_size`
- valid `number_of_milestones`
- relevant tags and languages
- non-milestone `[agent]` and `[verifier]`
- milestone `[[steps]]`, `[steps.agent]`, and `[steps.verifier]`
- `[environment]` limits and workdir

### Instruction Quality

Evaluates whether instructions:

- are clear and unambiguous
- state success criteria
- specify output formats
- include necessary context
- use absolute paths
- avoid hints

### Dockerfile

Checks:

- `WORKDIR /app`
- data file copying
- dependency installation
- solution/tests not copied into image
- no privileged operations
- pinned package and image dependencies

### Oracle Solution

Checks:

- shebang
- `set -euo pipefail`
- completeness
- determinism
- clarity
- no hardcoded final answers

### Tests and Test Runner

Checks:

- pytest usage
- multiple meaningful tests
- specific assertions
- helpful docstrings
- edge case coverage
- `tests/test.sh` writes `/logs/verifier/reward.txt`
- test dependencies are pinned

## Advanced Quality Checks

Agent Review also looks for:

- instruction/test behavior alignment
- anti-cheating measures
- structured data schema clarity
- dependency pinning
- naming consistency
- typos
- Docker and Harbor reserved-directory conflicts

## Critical Quality Rules

Must avoid:

- latency-based tests
- different verifier logic for oracle vs agent
- missing compose metadata flags
- web data fetching at runtime
- creating or modifying `/tests`, `/solution`, or `/oracle`
- exiting before reward is written
- missing defaults for variables such as `TEST_DIR`

## Severity Levels

### Critical

Must fix:

- missing required files
- invalid TOML
- missing metadata
- no test functions
- reward not written
- instruction/test behavior mismatch
- tests or solution copied to image
- hardcoded solution outputs
- unpinned language packages or floating base images
- missing structured data schema
- latency tests
- oracle/agent conditional logic
- web data fetching
- reserved directory creation

### Warning

Should fix:

- missing shebang
- unclear instructions
- unreasonable timeouts
- missing `WORKDIR`
- poor test docstrings
- test dependencies in Dockerfile
- minor typos
- questionable difficulty

### Suggestion

Optional improvements:

- code style
- additional tests
- docs
- naming

## Report Shape

```text
### Review Report: [task-name]

Status: PASS | WARNING | FAIL
Task Location: /path/to/task

Summary
Critical Issues
Warnings
Suggestions
Overall Assessment
Recommendation: READY TO USE | NEEDS FIXES | REQUIRES REVISION
```

## Acting on Feedback

1. Fix critical issues first.
2. Fix warnings next.
3. Consider suggestions.
4. Re-run local checks.
