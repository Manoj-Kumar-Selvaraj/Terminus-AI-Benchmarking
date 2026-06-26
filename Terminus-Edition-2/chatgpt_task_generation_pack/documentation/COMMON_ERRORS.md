# Common Errors

Use this page to spot frequent mistakes while creating or reviewing tasks.

## Instruction Problems

### Ambiguous Language

| Bad | Better |
|---|---|
| Make it better | Reduce runtime by a specific, testable amount |
| Fix the issues | Fix the three failing tests |
| Handle errors properly | Return HTTP 400 for invalid input |
| Optimize the code | Achieve a specified complexity or behavior |

### Relative Paths

Bad:

```markdown
Edit config/settings.json.
```

Good:

```markdown
Edit `/app/config/settings.json`.
```

### Missing Output Specs

Bad:

```markdown
Process the data and save results.
```

Good:

```markdown
Process `/data/input.csv` and save results to `/output/results.json`.
```

### Unverifiable Tool Requirements

Bad:

```markdown
Use vim to edit the file.
```

Good:

```markdown
Change the port from 8080 to 3000 in `/app/config.txt`.
```

## Test Problems

### Brittle String Matching

Bad:

```python
assert output == "Processing complete.\n"
```

Good:

```python
assert "complete" in output.lower()
```

### Implementation Testing

Bad:

```python
source = open("/app/main.py").read()
assert "sorted(" in source
```

Good:

```python
result = process_data()
assert result == sorted(result)
```

### Missing Docstrings

Bad:

```python
def test_1():
    assert process("") == []
```

Good:

```python
def test_empty_input_returns_empty_list():
    """Verify that empty input returns an empty list."""
    assert process("") == []
```

### Order-Dependent Tests

Bad:

```python
def test_1_setup():
    global data
    data = load_data()

def test_2_process():
    assert process(data)
```

Good:

```python
def test_process():
    data = load_data()
    assert process(data)
```

## Solution Problems

Hardcoded answer:

```bash
echo "The answer is 42" > /output/result.txt
```

Nondeterministic command:

```bash
ls /data/ > /output/files.txt
```

Better:

```bash
ls /data/ | sort > /output/files.txt
```

Missing error handling:

```bash
cd /nonexistent
do_something
```

Better:

```bash
set -e
cd /app
do_something
```

## Cheating Opportunities

### Exposing Test Logic

Bad:

```dockerfile
COPY tests/ /tests/
```

Tests should be mounted at runtime, not baked into the image.

### Answer in Git History

Bad:

```dockerfile
RUN git clone https://github.com/example/repo.git
```

Good:

```dockerfile
RUN git clone https://github.com/example/repo.git \
    && cd repo && git checkout abc123
```

### Editable Data Files

Bad:

```python
assert data["total"] == 42
```

Good:

```python
expected = sum(item["value"] for item in input_data)
assert output_data["total"] == expected
```

## Difficulty Issues

Too easy:

- single-step solution
- common tutorial topic
- simple API usage
- pattern matching succeeds

Too hard or unfair:

- requires unavailable information
- unreliable environment
- success depends on luck
- contradictory requirements

## Platform QC and Harbor Pitfalls (2026-05/06)

Recent reviewer and LLMaJ feedback on milestone tasks — fix these before zipping.

### Oracle `solve.sh` paths

Harbor mounts only the **current milestone** solution at `/solution/`. These paths **fail at runtime**:

```bash
bash /steps/milestone_1/solution/solve1.sh          # bad
bash "$SCRIPT_DIR/../../milestone_1/solution/solve1.sh"  # bad
```

Use `$SCRIPT_DIR/solveN.sh` in each milestone's `solve.sh`. Each `solveN.sh` must be a **standalone cumulative** fix for milestones 1 through N from the broken starter codebase. Do **not** call prior milestone `solve*.sh` scripts from inside `solveN.sh`. See [MILESTONE_ORACLE_SOLUTION_RULES.md](MILESTONE_ORACLE_SOLUTION_RULES.md).

### Dead oracle replacements

Every `text.replace(...)` in `solveN.sh` must match a string that **actually exists** in the starter source at that milestone. If the oracle fixes `loadOrderes` → `loadOrders` but the starter already spells `loadOrders`, the line is a no-op and QC flags it. Either introduce the typo in `environment/` source or remove the replacement.

### Misleading docs + instruction disclaimers

Red-herring docs under `environment/docs/` are valid anti-cheating. Do **not** tell the agent to ignore them in `instruction.md` — that weakens the measure. Let milestone instructions be authoritative; keep docs wrong or stale without a warning.

### Milestone date-schema backwards compatibility

When M3 adds optional date columns, the instruction must say: if both input files still use the earlier schema, keep prior matching behavior. Add a verifier test that writes **legacy headers** (no date columns) and asserts M2-style matching still works.

### `task.toml` milestone timeouts

Milestone tasks need **both** top-level `[agent]` / `[verifier]` defaults **and** per-step `[steps.agent]` / `[steps.verifier]` overrides. Some harnesses read global defaults before per-step values; omitting the top-level blocks fails schema checks.

```toml
[agent]
timeout_sec = 1800.0

[verifier]
timeout_sec = 900.0
```

Some portal reviewers ask to remove top-level blocks when per-step metadata exists; treat that as conflicting guidance and keep both unless the active submission schema explicitly forbids top-level blocks.

### `.dockerignore` for multi-directory builds

When `environment/Dockerfile` copies `src/`, `data/`, `config/`, `docs/`, etc., add `environment/.dockerignore` excluding `steps/`, `tests/`, `solution/`, caches, and build artifacts.

### Rubric score values

Allowed criterion scores: `{+1, -1, +2, -2, +3, -3, +5, -5}` only. Split milestone rubrics into per-step sections with behavior-focused wording (not "milestone N"). Penalize cheating via observable behavior (hardcoded outputs, bypassing the batch CLI) — never reference tests or reward files.

### Wire-consumption / deduplication tests

When testing one-time consumption, include **non-adjacent** duplicate returns (clear A, clear B, retry A → reject). Consecutive duplicates alone can pass with a "last cleared" shortcut.

### Offline submission: pytest in Dockerfile

When `allow_internet = false`, install `pytest` and `pytest-json-ctrf` in `environment/Dockerfile`. Remove `pip install` from milestone `test.sh` files.

Strict LLMaJ may still flag `test_deps_in_image`; for Edition 2 offline tasks this is expected structural noise unless a current platform reviewer explicitly says otherwise.

### Missing WORKDIR guard in `test.sh`

Every milestone `test.sh` should fail fast when the container has no working directory:

```bash
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi
```

Place this after initializing `/logs/verifier/reward.txt` and before `pytest`.

### Milestone oracle scope creep

Each `solveN.sh` should implement only that milestone's instructions. Do not add date/calendar logic in M2 when M3 owns it — dead variables and premature calendar parsing confuse reviewers and agents.

### Placeholder environment docs

Avoid `lib/*.txt` or `docs/*.md` files that contain only `"helper documentation only"` or two-line stubs. Either populate them with concise, accurate reference material or remove them from the image.

### Brittle oracle string patches

If an oracle script contains `text.replace(...)`, the searched string must exist in the starter source at that milestone. After cleaning starter typos or comments, rerun the oracle because exact patch strings may drift. Prefer a complete source rewrite for late milestones with substantial parsing/date/window logic.

### Legacy schema with new date/window columns

When a later milestone adds optional date columns, document and test both paths:

- both files omit the new columns entirely: preserve prior milestone behavior;
- columns exist but a row value is blank/missing: that row is ineligible.

### Field-specific alias config names

Avoid stale template filenames. If the field is `access_tier`, prefer `/app/config/access_tier_aliases.csv`; if the field is `lane_tier`, prefer `/app/config/lane_tier_aliases.csv`. Generic names like `kind_aliases.csv` are acceptable only when the instruction explicitly names them.

### Rubric refresh on every revision

Every changed task needs a fresh rubric pass, even for "minor" LLMaJ fixes. Ensure each milestone section has valid positive totals, at least one relevant negative criterion, allowed scores only, and criteria that reflect the final instruction/test behavior.
