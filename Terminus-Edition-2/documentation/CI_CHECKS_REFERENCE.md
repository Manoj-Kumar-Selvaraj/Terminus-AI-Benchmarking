# CI Checks Reference

All submissions must pass automated CI and LLMaJ checks.

Run locally:

```bash
harbor tasks check <task-folder> -m openai/@openai/gpt-5.2
```

## Static CI Checks

### pinned_dependencies

Checks that language-package dependencies use exact version pins.

Bad:

```dockerfile
RUN pip install numpy pandas
```

Good:

```dockerfile
RUN pip install numpy==1.26.4 pandas==2.1.0
```

Base images must use specific tags, not `latest`.

### typos

Checks spelling errors in file and variable names. Fix flagged typos.

### tests_or_solution_in_image

Checks that `tests/` and `solution/` are not copied into the Docker image.

Remove:

```dockerfile
COPY tests/ /tests/
COPY solution/ /solution/
```

### test_deps_in_image

Checks that test dependencies are installed in `tests/test.sh`, not the Dockerfile.

### check_dockerfile_references

Checks Dockerfile does not reference solution or test files.

Remove references to:

- `solution/solve.sh`
- `tests/test.sh`
- `test_outputs.py`

### check_test_sh

Checks that `tests/test.sh` uses `uv` and produces reward.

Reward must be written to:

```text
/logs/verifier/reward.txt
```

### check_task_absolute_path

Checks that instructions use absolute paths.

Bad:

```markdown
Edit config/settings.json
```

Good:

```markdown
Edit /app/config/settings.json
```

### check_privileged_containers

Checks that compose does not use privileged containers.

Remove:

```yaml
privileged: true
```

### ruff

Checks Python linting.

```bash
ruff check <task-folder>
ruff check --fix <task-folder>
```

### check_task_sizes

Checks file sizes. Remove or compress files above limits.

### validate_task_fields

Checks required `task.toml` fields.

## Quick Reference

| Check | Meaning | Fix |
|---|---|---|
| `pinned_dependencies` | exact versions | add version pins |
| `typos` | spelling | correct flagged items |
| `tests_or_solution_in_image` | no test/solution in image | remove COPY commands |
| `test_deps_in_image` | test deps in `test.sh` | move deps out of Dockerfile |
| `check_dockerfile_references` | no forbidden refs | remove solution/test refs |
| `check_test_sh` | uv and reward | fix test runner |
| `check_task_absolute_path` | absolute paths | use `/full/path` |
| `check_privileged_containers` | no privileged mode | remove privileged settings |
| `ruff` | lint passes | run ruff |
| `check_task_sizes` | size limits | remove/compress large files |
| `validate_task_fields` | metadata complete | add missing fields |

## LLMaJ Checks

For details, see [LLMAJ_CHECKS_REFERENCE.md](LLMAJ_CHECKS_REFERENCE.md).

Common LLMaJ checks:

- `behavior_in_task_description`
- `behavior_in_tests`
- `informative_test_docstrings`
- `anti_cheating_measures`
- `hardcoded_solution`
- `file_reference_mentioned`
- `structured_data_schema`

These checks evaluate quality and alignment, not just syntax.
