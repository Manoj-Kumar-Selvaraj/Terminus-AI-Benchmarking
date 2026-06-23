# Terminus 2nd Edition Platform Submission Guide

Use this guide when submitting tasks through the Snorkel Expert Platform instead of the `stb submissions create` CLI flow. Before every submission, run through [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md).

For rubric editing rules, see [RUBRICS_GUIDE.md](RUBRICS_GUIDE.md).

## High-Level Workflow

```text
1. Download skeleton
2. Extract and rename
3. Write instructions and metadata
4. Configure Docker environment
5. Test solution locally
6. Write oracle solution
7. Write verifier tests
8. Run oracle
9. Run real agents
10. Run LLMaJ checks
11. Final verification
12. Create ZIP
13. Submit to platform
14. Review CI and generated rubric
15. Send to reviewer
16. Monitor status
```

## Prerequisites

Before starting, make sure you have:

- Docker Desktop installed and running.
- Harbor CLI installed, or access to Harbor commands.
- API key for running agents.
- Access to the Snorkel Expert Platform.
- Access to the `Terminus-2nd-Edition` project.

## Step 1: Download the Correct Task Skeleton

Choose the skeleton that matches the task type:

- Regular task skeleton: use for non-UI and non-milestone tasks.
- UI task skeleton: use for all `ui_building` subtype tasks.
- Milestone task skeleton: use for tasks with milestones.

There are three task skeletons:

- Regular Task Skeleton ZIP.
- Milestone Task Skeleton ZIP.
- UI Task Skeleton ZIP.

## Step 2: Extract and Rename

Extract the ZIP file to your desired location.

Rename the folder to match your task name using kebab-case:

```text
fix-memory-leak-python
```

## Step 3: Write Instructions and Configuration

Author `instruction.md` using the Edition 2 prompt styling rules:

- concise
- well specified
- interesting
- no answers or hints
- unique
- absolute paths only

Configure `task.toml`:

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "unknown"
category = "software-engineering"
subcategories = []
number_of_milestones = 0
codebase_size = "minimal"
languages = ["bash"]
tags = ["file-operations"]
expert_time_estimate_min = 60
junior_time_estimate_min = 120

[verifier]
timeout_sec = 450.0

[agent]
timeout_sec = 900.0

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
```

Subcategory options:

- `long_context`
- `tool_specific`
- `api_integration`
- `db_interaction`
- `ui_building`

For `tool_specific`, `api_integration`, and `db_interaction`, include the specific tool, API framework, or database software in `tags`.

Codebase size:

- `minimal`: 0-20 files
- `small`: 20+ files
- `large`: 200+ files

Count all files in `environment/`.

## Step 4: Configure Docker Environment

Edit `environment/Dockerfile` to set up the task environment.

Rules:

- Add all task dependencies.
- Pin package versions for reproducibility.
- Never copy `solution/` or `tests/` into the Docker image.
- Keep task data and build files inside `environment/`.
- Prefer single-container tasks unless multiple containers are genuinely required.

For Docker issues:

- Ensure Docker Desktop is running.
- On macOS, enable **Allow the default Docker socket to be used** in Docker Advanced Settings.

If needed on macOS:

```bash
sudo dscl . create /Groups/docker
sudo dseditgroup -o edit -a $USER -t user docker
```

## Step 5: Test Your Solution Locally

Enter the task container interactively:

```bash
harbor tasks start-env -p <task-folder> -i
```

Use the container to validate your intended solution approach before writing the oracle.

## Step 6: Create Solution File

Create `solution/solve.sh` with the verified command sequence.

The oracle solution:

- proves the task is solvable
- must be deterministic
- should demonstrate the real command sequence
- should not merely output the final answer

For milestone tasks, each milestone has its own solution directory:

```text
steps/milestone_N/solution/
|-- solve.sh
`-- solveN.sh
```

`solve.sh` is the wrapper. `solveN.sh` is the actual oracle solution scoped only to that milestone.

## Step 7: Write Tests

Create `tests/test.sh` and test files such as `tests/test_outputs.py`.

Rules:

- `test.sh` must write `/logs/verifier/reward.txt`.
- Tests must cover explicit prompt requirements.
- Tests must cover implicitly expected behavior and critical edge cases.
- Every prompt requirement should map to a test.
- Place test-only helper files under `tests/`.

Example `test.sh`:

```bash
#!/bin/bash

apt-get update
apt-get install -y curl

curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh
source $HOME/.local/bin/env

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi

uvx \
  -p 3.13 \
  -w pytest==8.4.1 \
  -w pytest-json-ctrf==0.3.5 \
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

For milestone tasks, each milestone has its own tests directory:

```text
steps/milestone_N/tests/
|-- test.sh
`-- test_mN.py
```

`test_mN.py` should include a `TestMilestoneN` class and should score only that milestone.

## Step 8: Run Oracle Agent

Verify that the oracle passes:

```bash
harbor run -a oracle -p <task-folder>
```

This must pass before continuing.

## Step 9: Test With Real Agents

Set API credentials:

```bash
export OPENAI_API_KEY=<your-portkey-api-key>
export OPENAI_BASE_URL=https://api.portkey.ai/v1
```

Run GPT-5.2:

```bash
harbor run -a terminus-2 -m openai/@openai/gpt-5.2 -p <task-folder>
```

Run Claude Opus 4.6:

```bash
harbor run -a terminus-2 -m anthropic/@anthropic/claude-opus-4-6 -p <task-folder>
```

Run each agent two or three times to estimate pass rate. The task should have less than an 80% pass rate to be accepted.

## Step 10: Run LLMaJ Checks Locally

**Edition 2 reworked tasks (recommended):** strict dual-model check via Portkey:

```powershell
$env:OPENAI_API_KEY = "your-portkey-key"
$env:OPENAI_BASE_URL = "https://api.portkey.ai/v1"
python scripts/run_llmaj_litellm.py <task-folder-name> --strict
```

Defaults: `openai/gpt-5.4` + `openai/claude-opus-4-7`. Report: `reworked-tasks-v2/llmaj-reports/<task>_strict_llmaj.json`. See `documentation/LLMAJ_CHECKS_REFERENCE.md`.

**Platform parity (single model, requires Harbor/stb):**

```bash
harbor tasks check -m openai/@openai/gpt-5.2 harbor_tasks/<task_name>
```

All high-severity checks should pass before submission.

## Step 11: Final Verification

Before submitting, verify:

- Oracle agent passes.
- LLMaJ checks pass.
- Real-agent pass rate is below 80%.
- Required files are present.
- Task metadata is complete.
- Tests and instructions are aligned.
- Rubric expectations match the task.

Useful commands:

```bash
harbor run -a oracle -p <task-folder>
harbor tasks check -m openai/@openai/gpt-5.2 harbor_tasks/<task_name>
```

## Step 12: Create ZIP File

Important: ZIP the individual files inside your task folder, not the containing folder itself.

Non-milestone task layout:

```text
.
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

Milestone task layout:

```text
.
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

On macOS:

- Open the task folder.
- Select all files with `Cmd+A`.
- Right-click and compress.

On Windows:

- Open the task folder.
- Select all files with `Ctrl+A`.
- Right-click, then **Send to -> Compressed folder**.

## Step 13: Submit to Platform

In the Snorkel Expert Platform:

1. Go to `Terminus-2nd-Edition`.
2. Click **Start** on the Submission node.
3. Upload the ZIP file.
4. Keep **Send to reviewer** unchecked.
5. Check the rubrics checkbox.
6. Submit.

## Step 14: Review CI Results and Generated Rubric

After notification that the submission is back in your revision queue:

1. Open the task from the platform home screen.
2. Click **Revise**.
3. Check CI results.
4. Update the task if needed.
5. Review the generated rubric.
6. Edit the rubric for accuracy and completeness.
7. Re-upload a new ZIP if necessary.
8. Keep **Send to Reviewer** unchecked.
9. Submit again.

Use the reviewer checklist to confirm high-severity review criteria are addressed.

If you make significant task changes, update the rubric so it matches the current task.

## Step 15: Submit to Reviewer

After CI looks good and the task is back in your revision queue:

1. Open the task from the platform home screen.
2. Click **Revise**.
3. Check CI results.
4. Check and edit the rubric for accuracy.
5. Check **Send to Reviewer**.
6. Submit.

## Step 16: Monitor Status

Peer review usually takes one to three business days.

Automated checks run immediately. Feedback is provided if changes are needed. Acceptance happens when all criteria are met.

If changes are requested:

- Read the feedback carefully.
- Make requested changes locally.
- Re-run all checks.
- Create a new ZIP.
- Resubmit.

## Common Issues

### ZIP Structure Wrong

Problem: files are nested inside an extra folder.

Fix: ZIP the files directly, not the containing task folder.

### Missing Files

Problem: a required file was not included.

Fix for non-milestone tasks: verify the ZIP contains `instruction.md`, `task.toml`, `environment/`, `solution/`, and `tests/`.

Fix for milestone tasks: verify the ZIP contains `task.toml`, `environment/`, and one `steps/milestone_N/` directory per milestone. Each milestone directory must contain:

- `instruction.md`
- `tests/test.sh`
- `tests/test_mN.py`
- `solution/solve.sh`
- `solution/solveN.sh`

Milestone ZIPs should not contain root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md`.

### CI Fails After Upload

Problem: local checks passed, but platform CI fails.

Fix: check for environment differences and re-run locally with the exact CI commands.

### Docker Build Fails

Problem: Docker build fails on platform but works locally.

Fix:

- Pin application dependencies such as `pip`, `npm`, or similar packages to exact versions.
- Use a specific Docker base image tag instead of `latest` or another floating tag.
- Use specific image tags in `docker-compose.yaml`.
- Digest pins are no longer required.
- Check for platform-specific differences.
