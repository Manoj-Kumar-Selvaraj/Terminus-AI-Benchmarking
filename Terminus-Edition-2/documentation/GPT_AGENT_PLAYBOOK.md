# GPT/Codex Agent Playbook for Terminus Edition 2 Revisions

Field notes that the standard docs underplay. Feed this whole file as system/context to any GPT or Codex agent working on Terminus Edition 2 tasks. Every item below is a real trap that has cost a revision cycle.

---

## 1. How to think about a revision

Non-negotiable workflow for every task revision:

1. Read `task.toml`, `rubric.txt`, milestone instructions, tests, solutions, Dockerfile, and agent-visible docs.
2. Patch the reported issue and any obvious sibling issue inside the same task.
3. Refresh `rubric.txt` after the code/test/instruction change.
4. Run preflight.
5. Run the cumulative oracle for the task language/family.
6. Rebuild the zip with `scripts/zip.sh` (add `--include-rubric` only when explicitly requested).
7. Verify the zip contains `task.toml` and `rubric.txt` at the archive root.

A revision has two inputs you must reconcile:

1. **Snorkel Platform reviewer comments** (human reviewer) — usually 1-3 concrete complaints. Treat each as a contract: it must be visibly fixed in the diff.
2. **Agent review report** (auto-LLM reviewer) — usually flags Dockerfile bloat, dependency/runtime issues, or verifier-script problems. Treat its "Weaknesses" list as mandatory fixes, but check for outdated dependency guidance against the latest project announcement.

If the reviewer says "the task gets easier with my fix, raise the difficulty" — add tests, do not lengthen the prompt. Difficulty in Edition 2 comes from coverage, not verbosity.

If the difficulty report says **TRIVIAL** or both strong agents solve every run, do not make the prompt longer. First identify why the fix is too local: one obvious bug, happy-path-only tests, aliases/date variants of the same matcher, or no cross-row state. Increase difficulty through a new tested behavior surface:

- add a milestone only when it introduces a real interaction, not another copy of the same edge case;
- add config-driven behavior, candidate ranking, row consumption, replay/idempotency, stale-state recovery, old-schema compatibility, or tie-breaking rules;
- test conflicts between rules, such as wildcard matching plus disabled config plus date gates;
- update the oracle to compute the behavior, not write final outputs;
- keep the instruction short and natural, then ensure every new rule has a focused test.

Example pattern for a trivial matcher: add `/app/config/methods.csv` as an enabled-service policy, add `ANY` as a wildcard input value, rank candidates by latest date, configured priority, then source row, and assert unmatched report fields stay blank. That is real difficulty; adding five more alias tests is usually not.

Always **read the file before claiming a fix is needed.** Reviewer comments routinely describe an earlier version of the task. If the instruction already says what the reviewer asked for, your job is to make it more prominent (own paragraph, explicit "do not do X" clause), not to add it from scratch.

---

## 2. Instruction wording traps

### 2a. Spell out on-disk literals

When the codebase exposes a constant like `StatusPosted Status = "BOOKED"` in `types.go`, agents will "helpfully" rename the comparison to `"POSTED"` and break the test. Fix: a dedicated sentence in the instruction.

> The `status` column in `/app/data/classes.csv` stores the posted state as the literal string `BOOKED`. Do not rename or remap this literal.

Apply this rule for any string that exists in two forms (domain name vs. on-disk literal): give the literal its own sentence and forbid the mapping.

### 2b. Distinguish input column from output column when they share a name

If both `classes.csv` and `refund_report.csv` have a `status` column, agents conflate them and write `BOOKED` into the report. Always restate output values explicitly:

> The `status` column in `/app/out/refund_report.csv` uses only `MATCHED` or `UNMATCHED`. It must never contain `BOOKED` or the classpass status.

### 2c. Milestone instructions are cumulative AND self-contained

M2 must restate every M1 invariant the agent still has to honor. M3 must restate M2's aliases. The reason: each milestone is graded independently, and the agent may not have the M1 instruction in context. Repetition is correct, not redundant.

### 2d. Absolute paths only

`/app/data/classes.csv` ✓. `./data/classes.csv` ✗. The `check_task_absolute_path` CI check enforces this, and reviewers downgrade for relative paths even when CI misses them.

### 2e. No hints, no canary strings

Never write "first inspect X, then edit Y." Never include canary tokens. The prompt states what must be true, not how to get there.

---

## 3. Test-coverage traps

### 3a. Every alias / every enum value needs its own dedicated test

A single test that bundles `YG, SP, HT` aliases is **not** sufficient. Reviewers want one test per alias so a partial implementation (e.g. agent handled SP and HT but not YG) gets caught with a specific failing test name. Pattern:

```python
def test_yg_alias_matches_yoga_classpass_and_reports_canonical_studio():
    """A YG refund must match a BOOKED YOGA classpass and emit YOGA as the studio."""
    ...
```

Plus the combined test for interaction coverage.

### 3b. Add explicit anti-conflation guards

When two columns share a name (see 2b), add a test whose assertion *would catch the conflation*:

```python
statuses = [row["status"] for row in rows]
assert set(statuses).issubset({"MATCHED", "UNMATCHED"})
assert "BOOKED" not in statuses
```

This converts a soft instruction into a hard test failure.

### 3c. Every test function MUST have a docstring

`informative_test_docstrings` is an LLMaJ check. No docstring → revision. The docstring should describe **behavior under test**, not "tests function X."

### 3d. Tests overwrite input CSVs at runtime

Pattern: every test calls `write_inputs(...)` to replace `/app/data/*.csv` before invoking the binary. This is the standard anti-cheat: the agent cannot precompute outputs from the shipped data. Keep this pattern.

### 3e. Build Go binary in a session-scoped fixture, not in test.sh

```python
@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()
```

Keeps test.sh minimal and consistent across tasks.

### 3f. Use `/usr/local/go/bin/go` with PATH fallback

```python
GO = Path("/usr/local/go/bin/go")
go_cmd = str(GO) if GO.exists() else "go"
```

The `golang:1.22.12-bookworm` base image installs to `/usr/local/go/bin/`. Bare `go` works too via PATH but the explicit path makes the test resilient to PATH-stripping in some sandboxes.

---

## 3b. Ruby tasks

For every `ruby-*` task, follow [RUBY_TASK_TEMPLATE.md](RUBY_TASK_TEMPLATE.md): digest-pinned `ruby:3.3.5-slim`, baked pytest in the image, canonical `test.sh` (no `set -e`, no trap), top-level `[agent]`/`[verifier]` timeouts in `task.toml`, and milestone `solution/` folders that are self-contained (Harbor mounts only `/solution/` per step).

Normalize before zip: `python3 scripts/normalize_ruby_tasks.py`.

---

## 4. Dockerfile traps

### 4a. Keep tmux, drop asciinema/curl unless the task uses them

`tmux` is required by the agent harness. If model runs fail with `verifier_did_not_run` and `RuntimeError: Failed to start tmux session`, the task image is usually missing `tmux`.

Drop `asciinema`, `curl`, and other old-template extras unless the task uses them. For Go/Ruby verifier tasks, a typical apt list is `python3 python3-pip tmux ca-certificates`; add more only with a written reason.

### 4b. Verifier dependencies belong in the Docker image

Latest project guidance requires `allow_internet = false`, so verifier runtime internet is blocked. `test.sh` must not install or download dependencies with `apt-get`, `pip`, `curl`, `uv`, `npm`, or similar tools.

Bake required verifier dependencies into `environment/Dockerfile` instead. For Python verifiers using `--ctrf`, installing pinned packages in the image is acceptable:

```dockerfile
RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5
```

Older docs and agent-review outputs may still say to move test dependencies into `test.sh`; treat that as stale unless task-specific reviewer feedback says otherwise.

### 4c. Only include `uv` if the offline verifier actually needs it

If a task still uses `uvx`, copy `uv` from a pinned image and pre-warm everything during Docker build. Do not download packages at verifier runtime.

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/
```

No curl installer, no PATH gymnastics, version-pinned image reference. Verify the exact `uvx` flags supported by the pinned `uv` version; older notes using `-w` may not work with every `uvx`.

### 4d. Pre-install or pre-warm verifier dependencies at build time

Because `allow_internet = false` is required, anything `test.sh` needs must already be present in the image. The simplest current pattern for Python verifiers is to install pinned pytest packages in Dockerfile. If using `uvx`, pre-warm the cache during build with flags supported by the pinned `uv` version.

```dockerfile
RUN python3 -m pytest --version
```

### 4e. Pin everything

Base image digests are now enforced by static checks. A version tag alone is not enough:

```dockerfile
FROM golang:1.22.12-bookworm
```

Pin the same platform image by digest:

```dockerfile
FROM golang:1.22.12-bookworm@sha256:1f298b0c9fecdf504389a0329236f948cc04a566a2bb32337207cbaaa2f8177c
FROM ruby:3.3.5-slim@sha256:25a9df53c6f23406f6bc87426ad5bd74b6d99423a8c2ca630f2443dee2447f53
```

Use the linux/amd64 manifest digest when is present. After changing the Dockerfile, rebuild the zip; stale zips commonly keep the old unpinned `FROM` line. Apt packages are usually fine unpinned. Pip/uv packages still need exact `==` versions. No `latest` anywhere.

Also add `environment/.dockerignore` whenever `environment/` contains more than the Dockerfile:

```text
.git
.gitignore
**/__pycache__/
**/*.pyc
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/node_modules/
```

### 4f. Never `COPY solution/ /app/` or `COPY tests/ /app/`

`tests_or_solution_in_image` is a CI check. Solution and tests are mounted at runtime by Harbor into `/oracle/` and `/tests/`. Baking them in is an automatic fail.

---

## 5. The canonical test.sh template

Use this shape. Do not install dependencies here. Only the test-file path changes between milestones.

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m1.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Notes:
- `set -uo pipefail` (no `-e`) so the script continues past pytest's nonzero exit to write `reward.txt`. Using `-e` here is a silent stuck-task bug.
- Always pre-write `0` to reward, then upgrade to `1` on success. Reward file MUST exist for Harbor to count the run.
- `test.sh` must not run package installers or download tools at runtime.

---

## 6. Rubric traps (Snorkel Platform UI)

### 6a. Score values

Allowed positives: `1, 2, 3, 5`. Allowed negatives: `-1, -2, -3, -5`. **Never use `4` or `-4`** — both are platform-rejected.

### 6b. Minimum negative count

At least **3** negative criteria. Under three triggers a platform validation error.

### 6c. What criteria must NOT reference

- `task.toml`
- `instruction.md`
- `/tests/` internals (test names, file paths)
- Oracle or NOP runs

Criteria must be judgable from the agent's **terminal trace** alone. "Agent reads /tests/test_m1.py" is a forbidden phrasing.

### 6d. Always include anti-cheat negatives

These three are nearly universal:

```
Agent hardcodes output CSV or JSON instead of fixing the reconciliation logic, -5
Agent edits or deletes files under /tests or /oracle, or alters /app/data input CSVs to coerce a pass, -5
Agent changes required output filenames, schemas, status labels, or summary JSON keys, -3
```

### 6e. Mirror positive criteria from instruction requirements

Every "must" in the instruction maps to a positive criterion. If the instruction says "use canonical studio for matched rows," there must be a positive criterion rewarding exactly that observed behavior. Reviewers spot-check this mapping.

### 6f. Where to put the rubric for the user

Save rubric text in a parallel `.txt` file next to the fixed zip in `Revision-Fixed/`:

```
Revision-Fixed/<task>_YYYYMMDD_HHMMSS_fixed.zip
Revision-Fixed/<task>_YYYYMMDD_HHMMSS_rubric_fixed.txt
```

The `.txt` is for the user to paste into the Platform UI. Match the format of `go-event-ticket-refund-matcher_*_rubric_fixed.txt` — one criterion per line, comma, score.

---

## 7. task.toml traps

- **No `id` field** — Edition 2 platform manages identity. Remove if present.
- **`codebase_size`**: only `small` (20+ files in `environment/`) or `large` (200+). `minimal` is blocked for new submissions. Pad with realistic supporting files in `docs/`, `samples/`, `scripts/` if needed.
- **`number_of_milestones`** must equal the number of `[[steps]]` blocks. Mismatch = CI fail.
- **`expert_time_estimate_min` / `junior_time_estimate_min`** — junior is typically 2-3× expert. Don't leave at defaults.
- **`difficulty`** is the *intended* model difficulty, but acceptance is gated by actual model pass rate. Aim hard (≤20% on worst of GPT-5.2 / Opus 4.6) or medium (20–60%). Python-heavy tasks must be hard.
- **`allow_internet = false`** is required under `[environment]`.

---

## 8. Milestone scaffold

Required per-milestone files (current `stb` format):

```
steps/milestone_N/
├── instruction.md
├── solution/
│   ├── solve.sh        # thin wrapper: bash "$SCRIPT_DIR/solveN.sh"
│   └── solveN.sh       # actual logic
└── tests/
    ├── test.sh         # canonical template from §5
    └── test_mN.py
```

**No** root-level `instruction.md`, `solution/`, `tests/`, or `milestone_x.md` on milestone tasks. Old `stb init` versions emit these; `stb` must be upgraded.

The `solve.sh` → `solveN.sh` indirection is convention; keep it.

---

## 9. Oracle solve.sh idioms

Two patterns dominate in this repo:

**Bug-fix milestones (debugging tasks):** `solveN.sh` patches `/app/cmd/.../main.go` via an inline `python3 <<'PY' ... PY` heredoc that does `text.replace(...)` chains. Then runs `/app/scripts/run_batch.sh` to build and execute. Keep `set -euo pipefail` at the top. Solve scripts must be deterministic and idempotent.

**Feature milestones:** edit or replace source files directly with `cat >` heredocs.

Either way: **no hardcoded final answers**. The solve script must make the code produce the right output by computation, not by writing the expected report directly. The `hardcoded_solution` LLMaJ check looks for this.

---

## 10. Running strict LLMaJ locally

Run strict LLMaJ on **one task at a time** after oracle passes and before zipping. This is separate from `terminus2_cli check` (single-model Harbor check).

### Setup (once per shell)

```powershell
$env:OPENAI_API_KEY = "your-portkey-key"
$env:OPENAI_BASE_URL = "https://api.portkey.ai/v1"
```

Use a Portkey key — not a raw OpenAI key — so Anthropic models route correctly.

### Run strict check

From `Terminus-Edition-2/`:

```powershell
python scripts/run_llmaj_litellm.py go-veterinary-visit-credit-matcher --strict
```

Defaults: **`openai/gpt-5.4`** + **`openai/claude-opus-4-7`**. A criterion fails if **either** model fails.

Report path:

```text
reworked-tasks-v2/llmaj-reports/<task-name>_strict_llmaj.json
```

Summarize all reports:

```powershell
python scripts/summarize_llmaj_reports.py
```

### Custom models

```powershell
python scripts/run_llmaj_litellm.py go-my-task --strict `
  --models "openai/gpt-5.4,openai/claude-opus-4-6"
```

Do **not** pass `--reworked` unless you mean to check every task in the reworked list.

### How to respond to failures

| Failure | Typical fix |
|---|---|
| `behavior_in_task_description` | Add explicit requirement to the **milestone** `instruction.md` that owns the test |
| `behavior_in_tests` | Add a focused test for the stated requirement |
| `informative_test_structure` | Fix test docstrings so they match assertions exactly |
| `typos` | Align names/paths, or document intentional misleading docs in M1 instruction |
| `test_deps_in_image` | Usually expected for offline Edition 2; keep pinned pytest in Dockerfile unless current reviewer says otherwise |
| `anti_cheating_measures` | Expected for local oracle (`steps/*/solution/`); strict LLMaJ always flags — not fixable without removing oracle |
| `hardcoded_solution` | Oracle must patch/build/run code, not `echo` final answers |

Fix **both-models agree** items first. Re-run oracle, then strict LLMaJ, then pack zip.

Current Edition 2 override: if strict LLMaJ flags `test_deps_in_image` only because pinned pytest packages are installed in `environment/Dockerfile`, keep them there for offline verifier reliability. Do not move dependency installation into `test.sh`.

Full check definitions: `documentation/LLMAJ_CHECKS_REFERENCE.md`.

---

## 11. CI / LLMaJ checks worth memorizing

| Check | What trips it |
|---|---|
| `pinned_dependencies` | `latest`, missing `==` versions |
| `tests_or_solution_in_image` | `COPY tests/` or `COPY solution/` in Dockerfile |
| `check_dockerfile_references` | Dockerfile copies a path that doesn't exist in build context |
| `check_test_sh` | test.sh doesn't write `/logs/verifier/reward.txt`, masks pytest status, or performs runtime dependency installs |
| `check_task_absolute_path` | Relative paths in `instruction.md` |
| `validate_task_fields` | Missing or wrong-typed fields in `task.toml` |
| `behavior_in_task_description` | Instruction is vague / doesn't define behavior |
| `behavior_in_tests` | Tests assert implementation details, not behavior |
| `informative_test_docstrings` | Missing or generic docstrings |
| `anti_cheating_measures` | No anti-cheat coverage (no input randomization, no /tests guard) |
| `hardcoded_solution` | `solve.sh` writes the expected output literally |
| `file_reference_mentioned` | Instruction references a file that doesn't exist |
| `structured_data_schema` | Tests don't lock down output JSON/CSV schema |

---

## 12. Naming and packaging conventions

- Fixed zip name: `<task-name>_YYYYMMDD_HHMMSS_fixed.zip`. Optional suffixes: `_v2`, `_static`.
- Rubric file: `<task-name>_YYYYMMDD_HHMMSS_rubric_fixed.txt` next to the zip.
- Both go in `Terminus-Edition-2/Revision-Fixed/`.
- Zip from inside the task folder so the archive's root entries are `instruction.md`, `task.toml`, `environment/`, etc. — **not** the task folder name itself. Verify by listing the zip.

Windows note: the filesystem is case-insensitive. `Revision-Fixed` and `revision-fixed` collide. The Linux container is case-sensitive, but submissions are zipped on Windows here, so internal paths inherit the case used on disk. Standardize on the existing repo casing.

---

## 13. The "verify before declaring done" checklist

Before re-zipping:

- [ ] Every reviewer bullet has a visible change in the diff.
- [ ] Each new test fails against the *unfixed* main.go (mental trace it).
- [ ] Each new test passes against the oracle (mental trace `solveN.sh` against your assertions).
- [ ] `task.toml` has `allow_internet = false` under `[environment]`.
- [ ] Dockerfile bakes pinned verifier dependencies needed for offline tests; `test.sh` performs no installs.
- [ ] `test.sh` matches section 5 template (PWD guard, reward.txt, no masking pytest exit code).
- [ ] No `solution/` or `tests/` referenced inside Dockerfile.
- [ ] `task.toml` has no `id`, has all required fields, `number_of_milestones` matches `[[steps]]`.
- [ ] Rubric file: >=3 negatives, no `+/-4`, no meta-refs, anti-cheat criteria present.
- [ ] Rubric file was reviewed after this revision and still matches all final milestone behavior.
- [ ] Strict LLMaJ run on this task only: `python scripts/run_llmaj_litellm.py <task> --strict`
- [ ] Zip root contains task files directly, not a wrapper folder.

---

## 14. When in doubt

- Read a sibling task in the same family (e.g. `go-marketplace-payout-matcher` for go-* matchers) and mirror its structure. Edition-2 tasks within a family are intentionally near-isomorphic.
- The existing test format and rubric format are stronger guides than the prose docs. Match the existing shape.
- If a reviewer comment seems wrong, default to making the wording more prominent rather than arguing. Cost-of-edit << cost-of-defending-submission.
