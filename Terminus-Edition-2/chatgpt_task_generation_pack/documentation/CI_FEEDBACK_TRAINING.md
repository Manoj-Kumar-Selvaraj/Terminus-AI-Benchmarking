# CI Feedback Training

Use CI and LLMaJ feedback to iterate until the task passes all checks.

## Workflow

```text
Run checks -> Identify failures -> Fix issues -> Re-run -> Repeat
```

Run checks (pick one):

**Strict LLMaJ — Edition 2 reworked tasks (Portkey, dual-model):**

```powershell
$env:OPENAI_API_KEY = "your-portkey-key"
$env:OPENAI_BASE_URL = "https://api.portkey.ai/v1"
python scripts/run_llmaj_litellm.py <task-name> --strict
```

**Harbor single-model:**

```bash
harbor tasks check <task-folder> -m openai/@openai/gpt-5.2
```

See `documentation/LLMAJ_CHECKS_REFERENCE.md` for defaults and failure handling.

Example output:

```text
CI Checks:
  ✓ pinned_dependencies
  ✗ check_task_absolute_path
  ✓ validate_task_fields

LLMaJ Checks:
  ✓ behavior_in_tests
  ✗ informative_test_docstrings
  ✓ anti_cheating_measures
```

## Fix One Issue at a Time

Start with static CI checks before LLMaJ quality checks.

Example:

```text
check_task_absolute_path
Line 3: "Edit config/settings.json"
Use absolute path: /app/config/settings.json
```

Fix the specific issue, then re-run checks.

## Error Messages Usually Include

- check name
- file and line number
- problem description
- suggested fix

Read the message carefully; it often tells you exactly what to change.

## Efficient Iteration Tips

- Fix easy static checks first.
- Run locally before platform upload.
- Make one fix at a time.
- Re-run checks after each meaningful change.
- Use [CI_CHECKS_REFERENCE.md](CI_CHECKS_REFERENCE.md) and [LLMAJ_CHECKS_REFERENCE.md](LLMAJ_CHECKS_REFERENCE.md) for check-specific fixes.

## Before Final Submission

- [ ] All CI checks pass.
- [ ] All LLMaJ checks pass.
- [ ] Oracle agent passes.
- [ ] Real agents tested.
- [ ] Difficulty verified.
- [ ] Rubric reviewed and edited.
