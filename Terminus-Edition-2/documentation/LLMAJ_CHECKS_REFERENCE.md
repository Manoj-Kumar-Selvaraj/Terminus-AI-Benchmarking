# LLMaJ Checks Reference

LLM-as-Judge (LLMaJ) checks evaluate task quality beyond syntax: fairness, completeness, test/instruction alignment, and oracle design.

## Run locally (Terminus Edition 2 — recommended)

Use the Portkey-backed strict checker for reworked tasks. It runs **two models** and fails a criterion if **either** model fails (strict mode).

### Prerequisites

1. Portkey API key with access to `openai/gpt-5.4` and `openai/claude-opus-4-7`
2. Python env with `litellm` installed (same env as Harbor/stb)
3. From `Terminus-Edition-2/`:

```powershell
# PowerShell (Windows)
$env:OPENAI_API_KEY = "your-portkey-key"
$env:OPENAI_BASE_URL = "https://api.portkey.ai/v1"

python scripts/run_llmaj_litellm.py go-my-task-name --strict
```

```bash
# Bash (WSL/Linux/macOS)
export OPENAI_API_KEY="your-portkey-key"
export OPENAI_BASE_URL="https://api.portkey.ai/v1"

python scripts/run_llmaj_litellm.py go-my-task-name --strict
```

### Defaults (strict mode)

| Setting | Value |
|---|---|
| Models | `openai/gpt-5.4` + `openai/claude-opus-4-7` |
| Pass rule | Both models must pass each criterion |
| Report | `reworked-tasks-v2/llmaj-reports/<task>_strict_llmaj.json` by default; new-task batches may use `new-tasks-v*/llmaj-reports/<task>_strict_llmaj.json` |

**Run one task at a time.** Do not use `--reworked` unless you intentionally want all reworked tasks checked. For new-task batches, keep reports in the matching batch folder such as `new-tasks-v5/llmaj-reports/`.

### Override models

```powershell
python scripts/run_llmaj_litellm.py go-my-task-name --strict `
  --models "openai/gpt-5.4,openai/claude-opus-4-6"
```

Notes:

- Use the **`openai/`** prefix for Anthropic models through Portkey (`openai/claude-opus-4-7`, not `anthropic/...`).
- `openai/gpt-5.5` may be blocked on some Portkey integrations; `gpt-5.4` is the tested default.
- Opus 4.7 rejects `temperature=0`; the script skips temperature for that model automatically.

### Summarize reports

```powershell
python scripts/summarize_llmaj_reports.py
python scripts/summarize_llmaj_reports.py reworked-tasks-v2/llmaj-reports
```

### Strict-mode rules (extra vs Harbor default)

The script applies these in addition to the standard Harbor rubric:

- When uncertain → **fail**
- `informative_test_structure`: any docstring/comment that does not match assertions → fail
- `typos`: any inconsistent path/name unless documented as intentional in `instruction.md`
- `anti_cheating_measures`: fail if `steps/*/solution/` exists (oracle scripts — expected locally, strict LLMaJ still flags)
- `test_deps_in_image`: strict LLMaJ may fail if pytest is installed in `environment/Dockerfile`; current Edition 2 offline practice keeps pinned pytest packages in the image and treats this as expected structural noise unless reviewer guidance says otherwise
- `behavior_in_task_description` / `behavior_in_tests`: every tested edge must be explicit in the milestone instruction; every instruction requirement needs a direct test

Treat **both-models agree** failures as highest priority. Some failures are structural under strict mode and should be recorded rather than "fixed" blindly:

- `anti_cheating_measures` for local milestone tasks, when `steps/*/solution/` exists but Dockerfile and `.dockerignore` exclude solutions from the runtime image.
- `test_deps_in_image` for offline Edition 2 tasks, when pinned `pytest` and `pytest-json-ctrf` are baked into `environment/Dockerfile` and `test.sh` performs no runtime installs.

---

## Run locally (Harbor / STB — platform parity)

When you have `stb` credentials and want the same check the platform uses:

```bash
stb harbor tasks check -m openai/@openai/gpt-5.2 -o output.json ./my-task-name
```

Or without stb:

```bash
harbor tasks check -m openai/@openai/gpt-5.2 -o output.json ./my-task-name
```

This uses a **single** model. For Edition 2 hardening work, prefer the strict dual-model script above.

---

## Checks

### behavior_in_task_description

Checks whether all behavior tested by verifiers is described in `instruction.md`.

Why it matters: agents can only do what they are told. Tests that check unstated behavior are unfair.

Fix:

- Review each test.
- Map each assertion to a requirement in `instruction.md`.
- Add missing requirements to the prompt, without adding solution hints.

### behavior_in_tests

Checks whether all behavior described in `instruction.md` is verified by tests.

Why it matters: untested requirements create gaps.

Fix:

- Review each prompt requirement.
- Add tests for uncovered requirements.
- Include important implicit behavior and edge cases.

### informative_test_docstrings

Checks whether test functions have docstrings explaining what they validate.

Bad:

```python
def test_output():
    ...
```

Good:

```python
def test_output_file_has_correct_format():
    """Verify output.json contains status and items fields."""
    ...
```

### anti_cheating_measures

Checks whether the task is difficult to shortcut.

Agents might try to:

- inspect test files for answers
- edit data files to pass tests
- delete or modify tests
- find solutions in git history

Fix:

- Do not expose test logic in the task image.
- Verify computation, not just final hardcoded values.
- Use checksums or independent validation when appropriate.
- Pin cloned repos to specific commits.

### structured_data_schema

Checks whether structured output schemas are fully described.

Fix by specifying exact schemas in `instruction.md`.

Example:

```markdown
Save `/output/result.json` with this structure:

{
  "status": "success" | "error",
  "count": <integer>,
  "items": [
    {"id": <integer>, "name": <string>}
  ]
}
```

### hardcoded_solution

Checks whether the oracle demonstrates a process rather than just outputting an answer.

Bad:

```bash
echo "42" > /output/result.txt
```

Good:

```bash
cd /app
python calculate.py input.txt > /output/result.txt
```

### file_reference_mentioned

Checks whether files required by tests are mentioned in `instruction.md`.

Fix:

```markdown
Save your results to `/output/analysis.json`.
```

## Quick Reference

| Check | Meaning | Fix |
|---|---|---|
| `behavior_in_task_description` | tests match instructions | add prompt requirements |
| `behavior_in_tests` | instructions have tests | add test coverage |
| `informative_test_docstrings` | tests have docstrings | document each test |
| `anti_cheating_measures` | hard to cheat | remove shortcuts |
| `structured_data_schema` | schema explicit | define exact format |
| `hardcoded_solution` | oracle shows process | derive answers |
| `file_reference_mentioned` | output files named | mention required paths |

## Debugging Failures

When LLMaJ fails:

1. Read the JSON report under `reworked-tasks-v2/llmaj-reports/`.
2. Check `by_model` — note which model failed and why.
3. Prioritize failures both models agree on (`summarize_llmaj_reports.py` highlights these).
4. Make a targeted fix (instruction, test, or Dockerfile — not rubric prose alone).
5. Re-run oracle, then re-run strict LLMaJ on **that task only**:

```powershell
python scripts/run_llmaj_litellm.py go-my-task-name --strict
```
