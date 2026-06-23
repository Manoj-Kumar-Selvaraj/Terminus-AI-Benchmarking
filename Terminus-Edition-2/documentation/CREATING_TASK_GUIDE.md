# Creating a Task

Use this guide to create a new Terminus Edition 2 task from a skeleton.

## Step 1: Download the Correct Skeleton

Choose one of the three skeletons:

- Regular Task Skeleton: non-UI and non-milestone tasks.
- UI Task Skeleton: `ui_building` subtype tasks.
- Milestone Task Skeleton: tasks with milestones.

Skeleton ZIPs are available from the project resources.

## Step 2: Extract and Rename

Extract the ZIP file.

Rename the folder using kebab-case:

Good:

- `parse-json-logs`
- `debug-python-import`
- `configure-nginx-ssl`

Bad:

- `task1`
- `my-task`
- `test`

## Non-Milestone Structure

```text
your-task-name/
|-- instruction.md
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   `-- build files
|-- solution/
|   `-- solve.sh
`-- tests/
    |-- test.sh
    `-- test files
```

## Milestone Structure

```text
your-task-name/
|-- task.toml
|-- environment/
|   |-- Dockerfile
|   `-- build files
`-- steps/
    |-- milestone_1/
    |   |-- instruction.md
    |   |-- tests/
    |   |   |-- test.sh
    |   |   `-- test_m1.py
    |   `-- solution/
    |       |-- solve.sh
    |       `-- solve1.sh
    `-- milestone_2/
        `-- ...
```

Milestone tasks have no root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md`.

## Next Steps

1. Write `instruction.md` using [PROMPT_STYLING_GUIDE.md](PROMPT_STYLING_GUIDE.md).
2. Configure `task.toml` using [TASK_COMPONENTS.md](TASK_COMPONENTS.md).
3. Build `environment/` using [DOCKER_ENVIRONMENT_GUIDE.md](DOCKER_ENVIRONMENT_GUIDE.md).
4. Write oracle solution using [ORACLE_SOLUTION_GUIDE.md](ORACLE_SOLUTION_GUIDE.md).
5. Write tests using [WRITING_TESTS_GUIDE.md](WRITING_TESTS_GUIDE.md).
6. Run oracle using [ORACLE_AGENT_GUIDE.md](ORACLE_AGENT_GUIDE.md).
7. Test agent performance using [TESTING_AGENT_PERFORMANCE.md](TESTING_AGENT_PERFORMANCE.md).
8. Run CI checks using [CI_CHECKS_REFERENCE.md](CI_CHECKS_REFERENCE.md).
