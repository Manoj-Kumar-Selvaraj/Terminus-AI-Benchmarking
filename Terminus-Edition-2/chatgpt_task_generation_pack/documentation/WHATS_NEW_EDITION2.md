# What's New in Terminus Edition 2

Terminus Edition 2 moves away from simple script-completion tasks and toward realistic engineering challenges. Returning Edition 1 contributors should expect deeper tasks, stricter structure, more authentic prompts, expanded metadata, milestone support, task subcategories, and trace-based rubrics.

## Big Picture Shift

Edition 2 tasks should feel like real work a developer or technical user would give to a coding agent:

- Diagnose a broken service or codebase.
- Modify files in a realistic environment.
- Use tools and terminal exploration.
- Produce a verifiable final state.
- Show good engineering process in the terminal trace.

The goal is not to make tasks hard through long instructions. The goal is to make them hard through realistic debugging, implementation, integration, data, or infrastructure complexity.

## Structural Changes

The core submission layout is still familiar:

```text
<task-name>/
|-- instruction.md
|-- task.toml
|-- environment/
|-- solution/
`-- tests/
```

Edition 2 adds stricter hygiene and clearer expectations.

### Directory Hygiene

Keep the parent task directory clean. Move all non-essential files into relevant subdirectories.

Good parent-level files:

- `instruction.md`
- `task.toml`
- `environment/`
- `solution/`
- `tests/`
- milestone files/directories when using the supported milestone format

Avoid packaging:

- local job logs
- temporary files
- caches
- extra notes
- generated archives
- parent-level data that belongs in `environment/`

### Containerization

Prefer single-container tasks unless multiple containers are genuinely required.

Multi-container tasks are still allowed, but do not over-index on them. If the task can be represented cleanly in one container, use one container.

When Docker Compose is necessary:

- Include `environment/docker-compose.yaml`.
- Set `custom_docker_compose = true` in `task.toml`.
- If the compose file has multiple services, also set `is_multi_container = true`.

### Language Diversity

Edition 2 places greater emphasis on non-Python languages. Python is still valid, but the task pool should include more language variety:

- C/C++
- Go
- Java
- JavaScript/TypeScript
- Bash/system tooling
- SQL
- COBOL or other legacy languages
- language-specific build systems and package managers

## Metadata Changes

`task.toml` has expanded to support more granular agent routing and task evaluation.

### New: Subcategories

Use `subcategories` for specific challenge types inside the broader category.

```toml
subcategories = ["tool_specific", "api_integration"]
```

If no subcategory fits, leave it empty:

```toml
subcategories = []
```

### New: Codebase Size

`codebase_size` describes the number of files in `environment/`.

Use:

- `minimal`: 0-20 files
- `small`: 20+ files
- `large`: 200+ files

Example:

```toml
codebase_size = "small"
```

### New: Number of Milestones

Always include `number_of_milestones`.

For non-milestone tasks:

```toml
number_of_milestones = 0
```

For milestone tasks, this value must equal the number of `[[steps]]` blocks declared in `task.toml`.

### Removed: Task ID

Do not include a task `id` in Edition 2 `task.toml`. The platform manages task identity.

### Edition 2 Metadata Shape

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "hard"
category = "security"
subcategories = ["tool_specific"]
languages = ["bash", "c"]
codebase_size = "small"
tags = ["security", "capabilities", "least-privilege", "linux"]
expert_time_estimate_min = 60.0
junior_time_estimate_min = 180.0
number_of_milestones = 0

[verifier]
timeout_sec = 300

[agent]
timeout_sec = 900

[environment]
build_timeout_sec = 300
cpus = 1
memory_mb = 2048
storage_mb = 10240
```

## Authentic Prompt Styling

Edition 2 instructions should sound like realistic prompts from engineers or technical users. The prompt should tell the agent what needs to be true, not how to solve it.

The six core principles:

- Task instructions must be concise.
- Task instructions must be well specified.
- Task instructions must be interesting.
- Task instructions must not give answers or hints.
- Task instructions must be unique.
- Task instructions must use absolute paths.

Good instructions:

- State the current problem.
- Name relevant files using absolute paths.
- Define required final behavior.
- Mention outputs the tests will check.
- Stay short unless the domain genuinely requires a spec.

Avoid:

- step-by-step solution guidance
- "first inspect X, then edit Y"
- hints that reveal the intended implementation
- huge requirement lists
- vague requests like "make it better"
- relative paths like `./app/config.json`

## Milestone-Based Tasks

Edition 2 supports larger sequential tasks through milestones.

Terminology: Harbor calls these multi-step tasks. Terminus docs call them milestones. The terms are interchangeable.

Milestones divide a complex engineering task into standalone sequential stages. The Harbor framework runs a verifier between agent runs, assigns incremental rewards, and only moves forward when the current milestone is validated.

### Milestone Rule

Each milestone must be a prerequisite for the next. A milestone task should not be a bag of unrelated subtasks.

Milestones provide:

- Sequential logic: the agent completes milestone 1 before milestone 2.
- Granular validation: each milestone has its own instruction, tests, and oracle solution.
- Better process scoring: the framework can reward partial progress.

Current `stb` milestone scaffolds should use the multi-step format with self-contained milestone subdirectories under `steps/`. If `stb init -t milestone` creates older root-level files such as `solveN.sh`, `test_mN.py`, or `milestone_x.md`, upgrade `stb`.

For milestone tasks:

- Include the correct milestone structure generated by current `stb`.
- Set `number_of_milestones` to the exact milestone count.
- Ensure the count matches the number of `[[steps]]` blocks in `task.toml`.
- Keep each milestone independently testable.
- Make each milestone necessary for the next.

## Task Subcategories

Edition 2 introduces subcategories for key challenge areas. A task can use multiple subcategories if appropriate.

### Long Context

Tasks that require models to use large context windows by reading large documents or codebases.

Examples:

- large Markdown, HTML, JSON, CSV, or log archives
- repository-wide reasoning
- long specification reconciliation

### Tool Specific

Tasks targeting specialized tools, SDKs, or APIs where models tend to underperform.

Examples:

- FFmpeg
- ImageMagick
- Graphviz
- Blender
- MLflow
- WandB
- QGIS
- Linux capabilities

### API Integration

Tasks involving building, interacting with, or debugging APIs.

Examples:

- Flask, Django, Express, Gin, Rails, Spring Boot
- auth middleware
- request validation
- broken route behavior
- service-to-service integration

### DB Interaction

Tasks that require gathering context or solving problems through database interaction.

Examples:

- SQL migrations
- PostgreSQL constraints
- SQLite data repair
- Redis behavior
- NoSQL queries
- vector or in-memory stores

### UI Building

Tasks that create, edit, or update a user interface.

Examples:

- fixing UI state behavior
- implementing a component
- updating a dashboard
- Playwright-verifiable frontend changes

## Rubrics

Edition 2 evaluates both final state and process trace.

Unit tests still verify deterministic final correctness. Rubrics evaluate how the agent solved the task using evidence from the terminal trace.

Rubrics are authored through the Snorkel Platform submission UI, not the CLI. Before submitting a task with `stb submissions create`, configure the rubric in the platform UI.

Good rubrics:

- Reward positive engineering behaviors.
- Penalize harmful or low-quality behaviors.
- Are objective and binary.
- Can be judged from terminal trace evidence.
- Do not depend on hidden evaluator state.

Examples of good rubric criteria:

```text
Agent inspects the failing service logs before modifying configuration, +2
Agent runs the repaired CLI against at least one non-trivial input file, +2
Agent modifies files under /app/data that the instructions said to preserve, -5
Agent repeats the same failing command three or more times without changing inputs, -1
```

Rubric criteria should not:

- Mention `task.toml`.
- Mention `instruction.md`.
- Reference `/tests/` internals.
- Refer to oracle or NOP runs.
- Award points for basic task metadata.

## Edition 2 Contributor Checklist

Before submitting:

- Parent directory contains only necessary task files.
- Task is single-container unless multi-container is clearly required.
- `task.toml` includes `subcategories`, `codebase_size`, and `number_of_milestones`.
- `task.toml` does not include a task `id`.
- Instructions are concise, realistic, unique, and use absolute paths.
- Instructions describe what to accomplish, not how to solve it.
- Non-Python language opportunities were considered.
- Milestones, if used, are sequential and independently validated.
- Rubric is configured in the platform UI before CLI submission.
- Final-state tests still verify real correctness.
