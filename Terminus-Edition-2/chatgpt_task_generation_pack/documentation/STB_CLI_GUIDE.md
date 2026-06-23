# Snorkel Terminal-Bench CLI Guide

The `stb` command-line tool provides an end-to-end workflow for creating, testing, submitting, reviewing, and adjudicating Terminal-Bench tasks. For the manual Snorkel Expert Platform upload flow, use [PLATFORM_SUBMISSION_GUIDE.md](PLATFORM_SUBMISSION_GUIDE.md).

Note: Windows is not supported.

## Installation

Prerequisites:

- Docker installed and running.
- `uv` package manager installed.

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `stb`:

```bash
uv tool install snorkelai-stb --find-links https://snorkel-python-wheels.s3.us-west-2.amazonaws.com/stb/index.html --python ">=3.12"
```

The `stb` command is installed globally. Restart your terminal if it is not immediately available.

Verify installation:

```bash
stb --version
stb --help
```

## Authentication

Log in:

```bash
stb login
```

This opens the Experts platform and displays the API key generation dialog. Click **Generate Key**, copy the key, and paste it into your terminal.

Refresh AI credentials if exhausted or expired:

```bash
stb keys refresh
```

View current credentials:

```bash
stb keys show
```

## Task Submission Workflow

Submission flow:

```text
1. Initialize -> 2. Develop -> 3. Test -> 4. Submit -> 5. Check Status -> 6. Iterate
```

### 1. Initialize Task

Find your assigned project:

```bash
stb projects list
```

Project role status meanings:

- `active`: you are assigned and the project is open.
- `inactive`: you are assigned but the project is closed.
- `unassigned`: you are not assigned to this role; contact an admin to request assignment.

Create a new task folder:

```bash
stb init my-task-name -p PROJECT_ID -t TEMPLATE_NAME
```

You can use either the project name or UUID. If a project has only one template, `-t` is optional.

Examples:

```bash
stb init my-task-name -p "Terminus-2nd-Edition" -t base
stb init my-task-name -p bfe79c33-8ab0-4061-9849-08d3207c9927 -t milestone
```

For non-milestone templates, such as `-t base`, `stb init` creates:

```text
my-task-name/
|-- instruction.md
|-- task.toml
|-- environment/
|   `-- Dockerfile
|-- solution/
|   `-- solve.sh
`-- tests/
    `-- test.sh
```

Milestone note: `-t milestone` should use the newer multi-step format with each milestone as a self-contained subdirectory under `steps/`. If it generates older root-level `solveN.sh`, `test_mN.py`, or `milestone_x.md` files, upgrade `stb` before proceeding.

### 2. Develop Your Task

Edit the generated files:

- `instruction.md`: task instructions.
- `task.toml`: metadata and configuration.
- `environment/Dockerfile`: environment setup.
- `solution/solve.sh`: oracle solution.
- `tests/test.sh`: verifier entrypoint.

Most tasks also need task-specific app/source/data files under `environment/` and pytest tests such as `tests/test_outputs.py`.

### 3. Test Locally

Start the task environment interactively:

```bash
stb harbor tasks start-env -p ./my-task-name -i
```

Run the oracle agent:

```bash
stb harbor run -a oracle -p ./my-task-name
```

Test with real agents:

```bash
stb harbor run -m @openai/gpt-5.2 -p ./my-task-name
stb harbor run -m @anthropic/claude-opus-4-6 -p ./my-task-name
```

Run each agent two or three times to estimate difficulty.

### 4. Submit

Before submitting, configure the rubric through the platform UI. The CLI does not include a rubric setup step.

Create a submission:

```bash
stb submissions create ./my-task-name -p PROJECT_ID --time MINUTES
```

Use `--time` for time spent in minutes, for example `--time 120` for two hours.

The CLI automatically:

- Zips the task folder.
- Uploads to the platform.
- Runs automated checks.
- Creates a submission record.

### 5. Check Submission Status

List your submissions for a project:

```bash
stb submissions list -p PROJECT_ID
```

Show local folder names too:

```bash
stb submissions list -p PROJECT_ID --show-folder-names
```

Submission status reference:

| Status | Meaning | Can Update? |
|---|---|---|
| `EVALUATION_PENDING` | Automated checks running | No |
| `NEEDS_REVISION` | Reviewer requested changes | Yes |
| `REVIEW_PENDING` | Waiting for a human reviewer | No |
| `ACCEPTED` | Task accepted | No |
| `OFFERED` | Offer made | No |
| `REJECTED` | Task rejected | No |
| `SKIPPED` | Task skipped | No |

Drill into a submission:

```bash
stb submissions view SUBMISSION_ID
stb submissions download SUBMISSION_ID
stb submissions feedback SUBMISSION_ID
```

Feedback usually includes:

- Agent-generated quality and difficulty check results.
- Notes from expert reviewers.

### 6. Iterate on Feedback

Update a submission in `NEEDS_REVISION`:

```bash
stb submissions update ./my-task-name -s SUBMISSION_ID --time MINUTES
```

If the submission was created with the CLI, the submission ID can be omitted:

```bash
stb submissions update ./my-task-name --time MINUTES
```

By default, submissions are sent to reviewers after evaluation passes. To skip reviewer notification:

```bash
stb submissions update ./my-task-name --time MINUTES --no-send-to-reviewer
```

## Task Review Workflow

Review flow:

```text
1. Get Assignment -> 2. Download -> 3. Review -> 4. Make Decision
```

Get a review assignment:

```bash
stb reviews get -p PROJECT_ID
```

List review assignments:

```bash
stb reviews list -p PROJECT_ID
```

Download a submission:

```bash
stb reviews download REVIEW_ID
```

View feedback:

```bash
stb reviews feedback REVIEW_ID
```

Open in browser:

```bash
stb reviews view REVIEW_ID
```

Accept:

```bash
stb reviews accept REVIEW_ID --time MINUTES
stb reviews accept REVIEW_ID --time MINUTES -n "Optional acceptance notes"
```

Request revision:

```bash
stb reviews revise REVIEW_ID --notes "Specific issues to address" --time MINUTES
```

Skip if not qualified:

```bash
stb reviews skip REVIEW_ID --reason REASON --rationale "Explanation"
```

Valid skip reasons:

- `outside_expertise`
- `unclear_or_ambiguous`
- `too_time_consuming`
- `invalid_input`
- `other`

## Task Adjudication Workflow

Adjudication flow:

```text
1. Get Assignment -> 2. Download -> 3. Adjudicate -> 4. Make Decision
```

Get an adjudication assignment:

```bash
stb adjudications get -p PROJECT_ID
```

List adjudication assignments:

```bash
stb adjudications list -p PROJECT_ID
```

Download a submission:

```bash
stb adjudications download ADJUDICATION_ID
```

View feedback:

```bash
stb adjudications feedback ADJUDICATION_ID
```

Open in browser:

```bash
stb adjudications view ADJUDICATION_ID
```

Accept:

```bash
stb adjudications accept ADJUDICATION_ID --time MINUTES
stb adjudications accept ADJUDICATION_ID --time MINUTES -n "Explanation of decision"
```

Request revision:

```bash
stb adjudications revise ADJUDICATION_ID --notes "Specific issues to address" --time MINUTES
```

Skip if not qualified:

```bash
stb adjudications skip ADJUDICATION_ID --reason REASON --rationale "Explanation"
```

Valid skip reasons:

- `outside_expertise`
- `unclear_or_ambiguous`
- `too_time_consuming`
- `invalid_input`
- `other`

## Additional Commands

Launch Claude Code with preconfigured platform AI credentials:

```bash
stb claude
```

## Troubleshooting

`This folder has already been submitted`:

- Use `stb submissions update` instead of `stb submissions create`.

`Cannot update: submission is in X state`:

- Only submissions in `NEEDS_REVISION` can be updated.
- Check current state with `stb submissions list`.

Docker issues:

- Ensure Docker Desktop is running.
- On macOS, enable **Allow the default Docker socket to be used** in Docker Advanced Settings.

API key issues:

- Run `stb login` to re-authenticate.

`Maximum refresh limit (3)` error:

- You exceeded the retry limit for AI credential requests.
- Contact an admin to reset your key refresh limit, then run `stb keys refresh` again.

Known harmless model warning:

```text
Failed to retrieve model info for '@anthropic/claude-opus-4-6'...
```

This warning can be ignored; testing should still work.

## Upgrading

The CLI checks for updates hourly. When available, it shows a message like:

```text
Update available: 2.0.2 -> 2.1.0
Run: uv tool upgrade snorkelai-stb --find-links https://snorkel-python-wheels.s3.us-west-2.amazonaws.com/stb/index.html --python ">=3.12"
```

Upgrade with:

```bash
uv tool upgrade snorkelai-stb --find-links https://snorkel-python-wheels.s3.us-west-2.amazonaws.com/stb/index.html --python ">=3.12"
```

Your config and credentials are preserved.

## Uninstallation

Uninstall the CLI:

```bash
uv tool uninstall snorkelai-stb
```

Optionally remove configuration:

```bash
rm -rf ~/.config/stb/
```

## Next Steps

- New to Terminal-Bench? Read What Makes a Good Task.
- Ready to create? Read Task Components and Platform Submission Guide.
- Before submitting, review the Submission Checklist.
- Need help? Check the FAQ or ask in Slack.
