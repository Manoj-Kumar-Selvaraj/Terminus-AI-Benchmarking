# Terminus 2nd Edition Quick Start

Use this guide to get ready to create, evaluate, and submit Terminus 2nd Edition tasks.

For a full table of contents, see [README.md](README.md).

## Prerequisites

Before creating tasks, make sure you have:

- Access to the Snorkel Expert Platform.
- Access to the `Terminus-2nd-Edition` submission node.
- Joined Slack channel `#terminus-2nd-edition submission`.
- Joined notification channel `terminus-2nd-edition-announcements`.
- Installed and configured the Snorkel CLI.
- Read the Snorkel CLI user guide.
- Docker Desktop `v24.0.0+` installed and running.

The Snorkel CLI lets you:

- Check submission status, such as accepted, pending review, or evaluation pending.
- Generate your API key.
- Refresh your API key.
- Submit tasks through the CLI instead of the platform, if desired.

For the full CLI workflow, including `stb init`, local Harbor runs, submissions, reviews, adjudications, troubleshooting, and upgrades, use [STB_CLI_GUIDE.md](STB_CLI_GUIDE.md).

## Recommended Setup With uv

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Harbor. Python `3.12` and `3.13` are supported; use `3.13` unless your environment requires otherwise:

```bash
uv tool install "harbor @ https://snorkel-public.s3.us-west-2.amazonaws.com/harbor/harbor-0.5.0%2Bpromptfix5-py3-none-any.whl" --python 3.13
```

Configure API keys after the Snorkel CLI is installed and your API key is generated:

```bash
export OPENAI_API_KEY=<your-portkey-api-key>
export OPENAI_BASE_URL=https://api.portkey.ai/v1
```

For persistence, add those exports to `~/.bashrc` or `~/.zshrc`.

## Manual Setup Notes

If you prefer a traditional `pip` installation or need more control, follow the manual platform setup instructions.

Recommended VS Code extensions:

- Docker
- Python
- Markdown
- TOML
- GitLens

## Next Steps

After setup:

- Read [WHATS_NEW_EDITION2.md](WHATS_NEW_EDITION2.md) if you are new to Edition 2 or returning from Edition 1.
- Use [PLATFORM_SUBMISSION_GUIDE.md](PLATFORM_SUBMISSION_GUIDE.md) if submitting through the Snorkel Expert Platform.
- Use [STB_CLI_GUIDE.md](STB_CLI_GUIDE.md) if submitting, reviewing, or adjudicating through the CLI.
- Read [GOOD_TASK_GUIDE.md](GOOD_TASK_GUIDE.md).
- Use [CREATING_TASK_GUIDE.md](CREATING_TASK_GUIDE.md) when starting from a skeleton.
- Check [TASK_COMPONENTS.md](TASK_COMPONENTS.md) and [TASK_REQUIREMENTS.md](TASK_REQUIREMENTS.md).
- Use [PROMPT_STYLING_GUIDE.md](PROMPT_STYLING_GUIDE.md) when writing `instruction.md`.
- Use [TASK_TAXONOMY.md](TASK_TAXONOMY.md) and [TASK_SUBTYPES.md](TASK_SUBTYPES.md) when setting metadata.
- Review [SUBMISSION_DIVERSITY_REQUIREMENTS.md](SUBMISSION_DIVERSITY_REQUIREMENTS.md) before starting a new task.
- Use [MILESTONES_GUIDE.md](MILESTONES_GUIDE.md) for milestone tasks.
- Use [RUBRICS_GUIDE.md](RUBRICS_GUIDE.md) before editing platform-generated rubrics.
- Use [DOCKER_ENVIRONMENT_GUIDE.md](DOCKER_ENVIRONMENT_GUIDE.md), [ORACLE_SOLUTION_GUIDE.md](ORACLE_SOLUTION_GUIDE.md), and [WRITING_TESTS_GUIDE.md](WRITING_TESTS_GUIDE.md) while building.
- Use [ORACLE_AGENT_GUIDE.md](ORACLE_AGENT_GUIDE.md), [NOP_AGENT_GUIDE.md](NOP_AGENT_GUIDE.md), [TESTING_AGENT_PERFORMANCE.md](TESTING_AGENT_PERFORMANCE.md), [CI_FEEDBACK_TRAINING.md](CI_FEEDBACK_TRAINING.md), [CI_CHECKS_REFERENCE.md](CI_CHECKS_REFERENCE.md), [LLMAJ_CHECKS_REFERENCE.md](LLMAJ_CHECKS_REFERENCE.md), and [AGENT_REVIEW_REFERENCE.md](AGENT_REVIEW_REFERENCE.md) while validating.
- Use [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) before submitting tasks.
- Use [QUALITY_GUIDELINES.md](QUALITY_GUIDELINES.md), [COMMON_ERRORS.md](COMMON_ERRORS.md), and [BAD_EXAMPLES.md](BAD_EXAMPLES.md) when self-reviewing.
- Use [REVIEW_GUIDELINES.md](REVIEW_GUIDELINES.md), [REVIEWER_CHECKLIST.md](REVIEWER_CHECKLIST.md), and [REVIEWER_TRAINING.md](REVIEWER_TRAINING.md) when reviewing tasks.
- Use [DEFENDING_SUBMISSION.md](DEFENDING_SUBMISSION.md) when responding to reviewer feedback.
- Use [FAQ.md](FAQ.md) for common project questions and known issues.
- Use [V1_V2_TASK_REFERENCE.md](V1_V2_TASK_REFERENCE.md) for local v1/v2 structure and pattern research.
