# Testing Agent Performance

Run real AI agents to validate difficulty and catch bad failure modes.

## Prerequisites

Use the Snorkel CLI to generate and refresh API credentials.

Set:

```bash
export OPENAI_API_KEY=<your-portkey-api-key>
export OPENAI_BASE_URL=https://api.portkey.ai/v1
```

## Models

| Model | CLI Name |
|---|---|
| GPT-5.2 | `@openai/gpt-5.2` |
| Claude Opus 4.6 | `@anthropic/claude-opus-4-6` |

## Run Agents With stb

```bash
stb harbor run -m @openai/gpt-5.2 -p <path-to-task>
stb harbor run -m @anthropic/claude-opus-4-6 -p <path-to-task>
```

Harbor command form:

```bash
harbor run -a terminus-2 -m openai/@openai/gpt-5.2 -p <task-folder>
harbor run -a terminus-2 -m anthropic/@anthropic/claude-opus-4-6 -p <task-folder>
```

## Interpreting Results

Pass:

- Agent completed the task.

Good fail:

- reasoning error
- missed subtle requirement
- lacked domain knowledge
- multi-step complexity caused mistakes

Bad fail:

- ambiguous instructions
- environment issue
- tests too strict
- missing required information

Bad failures mean the task needs revision.

## Determine Difficulty

Run each agent 5 times for reliable pass rate.

Example:

```text
GPT-5.2: 2/5 = 40%
Claude Opus 4.6: 0/5 = 0%
Worst-model accuracy: 0%
Difficulty: Hard
```

## Analyze Failures

When an agent fails:

- watch the terminal recording
- check the analysis
- read the debug pane
- inspect verifier output

Ask whether the failure is due to task difficulty or task quality problems.
