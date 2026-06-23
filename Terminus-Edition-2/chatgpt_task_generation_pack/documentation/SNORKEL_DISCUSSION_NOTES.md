# Snorkel Discussion Notes

Last updated: 2026-05-28

These are distilled operational notes from project-channel discussions. Treat them as live field context, not as a replacement for the official docs or task-specific reviewer feedback.

## Submission And Review Operations

- Medium tasks can be acceptable, especially in non-Python languages, but current acceptance still depends on measured model pass rate and diversity rules.
- TypeScript, Rust, Go, Ruby, Bash, and COBOL have all been used successfully in this workspace. Prefer the language that makes the task realistic and inspectable.
- New multi-container and UI-building tasks are being phased out and should not be started. Existing tasks already in pipeline/review/revision are grandfathered and should not be rejected or reworked solely because of this restriction.
- Daily submission limits may increase as acceptance improves and revision rates decrease. Do not assume a fixed high daily limit.
- Pending-review delays and dashboard/task-update lag can happen. Use platform status, downloaded feedback artifacts, and local evidence together.
- If a task is rejected because the oracle failed on the platform, download the difficulty/eval artifact and inspect the real failure reason. A local pass alone is not enough evidence.
- If local validation passes but Snorkel says difficulty checks failed, inspect the downloaded difficulty-check artifact and Summary/Common Failures section before changing task logic.
- The task database/status sheet may lag or have sync issues; do not use it as the only source of truth for technical fixes.

## Current Dependency Guidance

Latest project announcement: every `task.toml` must include `allow_internet = false` under `[environment]`. Runtime internet is blocked, so verifier scripts must not install or download dependencies while running.

- Do not use `apt-get install`, `pip install`, `curl`, `uv` installs, `npm install`, or similar dependency downloads inside `test.sh`.
- Bake all verifier/runtime dependencies into the Docker image through `environment/Dockerfile`.
- Keep dependencies pinned: language/application packages should use exact versions; Docker base images should be digest-pinned when current guidance requires it; apt packages do not need exact pins.
- Older docs and agent-review reports may still say to move verifier dependencies from Dockerfile into `test.sh`. Treat that as outdated unless current task-specific reviewer feedback says otherwise.
- If an automated review says "move pytest/pytest-json-ctrf into test.sh" while `allow_internet = false` is required, treat it as stale guidance and be ready to explain that verifier dependencies must be baked into the image.
- For Debian/apt packages, do not pin exact package versions unless there is a task-specific reason. Pin language packages such as pip/gem/npm/cargo dependencies instead.

Practical rule for this repo: verify the exact task locally under offline conditions. Do not blindly rewrite working Docker/test runners just to match an older template.

## Timeout And Environment Defaults (mandatory)

Every `task.toml` must include **both** top-level timeout blocks **and** per-milestone timeouts (when `[[steps]]` exist). This avoids portal 7200s completion-marker timeout failures.

```toml
[agent]
timeout_sec = 1800

[verifier]
timeout_sec = 900

[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"
```

Use `build_timeout_sec = 600.0` only when a task truly needs a shorter image build; otherwise prefer `900.0`.

Per-milestone blocks (repeat for each `[[steps]]`):

```toml
[[steps]]
name = "milestone_1"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
```

Bulk audit/fix: `python3 scripts/audit_fix_task_toml_timeouts.py` (add `--dry-run` to preview).

Ruby tasks: see [RUBY_TASK_TEMPLATE.md](RUBY_TASK_TEMPLATE.md) and run `python3 scripts/normalize_ruby_tasks.py` before zipping.

If a build times out after 7200 seconds:

- First suspect a Docker build step or verifier path trying to resolve/download something under blocked internet.
- Check whether package managers are doing hidden dependency resolution, including `pip`, `npm`, `bundle`, `go mod download`, `cargo`, `apt-get`, or curl-based installers.
- Check the Python and pytest/pytest-json-ctrf versions actually present in the image, especially when the platform fails but local runs pass.
- Include `FROM ...` where architecture mismatch has been a problem for the language image.
- Do not add `gpus = 0` blindly; only use schema-supported fields for the current task type.

## Reviewer-Facing Notes

When reviewing another task or responding with reviewer-facing notes:

- Read the review guidelines, review checklist, prompt-styling bad examples, and Boost workflow before making a review decision.
- Start with `Needs Revision.` or `Accept.`
- Keep the note short, self-contained, and actionable.
- Mention only the main blockers and most important cleanup items.
- Explain what is wrong, why it matters, and what should be fixed.
- Avoid severity sections, numbered findings, file-by-file pointer lists, long internal reasoning, unsupported claims, and generic comments.
- Avoid outdated dependency advice, especially blanket requests to move verifier dependencies out of Dockerfile.

Useful dependency wording when it truly applies:

```text
Please add allow_internet = false under [environment] in task.toml. Since verifier runtime internet is blocked, tests/test.sh should not install or download dependencies with pip, apt-get, curl, uv, npm, etc. Please bake all verifier dependencies into the Dockerfile/environment instead.
```

## Reviewer Quality Checklist

Instruction prompt styling is a top-priority review area:

- Instructions should feel like a natural prompt to a terminal coding agent.
- Prefer a couple of opening sentences that describe the problem or goal.
- Avoid excessive bullets, headers, titles, tables, heavy Markdown, step-by-step developer instructions, hints, and solving strategies.
- Describe what needs to be true, not how the agent should discover or implement it.

Test alignment:

- Every explicit requirement in the prompt should map to a test.
- Important implicit behavior and critical edge cases should be tested.
- Tests should not assert requirements that are neither explicit nor reasonably implied by the instructions.
- Reward must be binary: `0` when any test fails and `1` only when all tests pass. Partial rewards are not allowed.

Dependency pinning:

- Language/application dependencies should be pinned to exact versions.
- Docker base images should be pinned by digest when current reviewer guidance requires it.
- Apt packages do not need exact version pins.
- `allow_internet = false` is now required, so verifier dependencies should be available in the Docker image and not downloaded by `test.sh`.
- Dependency guidance has changed over time. If reviewing, use the latest platform guidance; if authoring, validate the exact task under offline verifier conditions.

Rubrics:

- Include at least three negative-reward criteria.
- Prefer positive-language criteria such as `Agent correctly implements X`.
- Do not mention oracle, NOP, test internals, `task.toml`, or `instruction.md`.
- Do not send a task back solely because the cumulative rubric range is outside 10-40; this may be handled programmatically.
- Do not include a `rubrics.txt` file inside the submission zip. Local paste-ready rubric files belong outside the zip, such as in `Revision-Fixed/`.

Milestones:

- Some newer reviewer guidance mentions individual `milestone_1.md`, `milestone_2.md`, etc. files and a root `instructions.md` that describes all milestones.
- The existing tasks in this workspace mostly use the current `steps/milestone_N/` Harbor structure. Existing submissions already in the pipeline may be exempt from newer milestone-file expectations.
- Before changing milestone structure, check whether the task is net-new or already in a revision/review queue and follow the active schema for that submission.

Source-code hints:

- Flag environment comments that label bugs or reveal solutions, such as `BUG 7: Enabled is string instead of bool`.
- Bugs should be discoverable through realistic code behavior, tests, docs, and logs, not through explicit labels.

Reviewer scope:

- Reviewers should focus on submission quality, correctness, prompt/test alignment, reproducibility, oracle/verifier quality, and anti-cheat concerns.
- Diversity restrictions such as codebase size, language distribution, and difficulty filtering are generally enforced automatically and should not dominate manual review decisions.
- Acceptance/revision UI checkboxes for very high quality or very low quality/spam should be used when appropriate, but written notes still need to be self-contained.

## Difficulty Failures

Difficulty thresholds should be evaluated in this order: hard, then medium, then easy. Stop at the first category that matches.

- Hard if accuracy is `<= 20%` on the best model.
- If that does not apply, hard if accuracy is `<= 20%` on the worst model.
- Medium if worst-model accuracy is `> 20%` and `<= 60%`.
- Easy if worst-model accuracy is `> 60%` and `<= 80%`.

Example: if Claude is `5/5` and GPT-5.2 is `1/5`, the best-model hard rule fails, but the worst-model hard rule passes, so the task is hard.

If the platform reports `TRIVIAL - Requires at least MEDIUM`:

- Do not try shallow hardening or longer instructions.
- Preserve tests/behaviors that already caused partial failures.
- Replace tests that every agent solved easily.
- Increase difficulty through real interaction complexity: state recovery, idempotency, ordering-sensitive behavior, persistence, delayed-effect bugs, cross-module dependencies, or subsystem interactions.
- Keep instructions concise; hide complexity in runtime behavior and edge cases, not wording.
- Re-run oracle, NOP, static checks, and model/difficulty checks after reconstruction.

If the report says some tests were not passed by any agent run:

- Check whether the task is unsolvable, underspecified, or has verifier/environment failures.
- Inspect the summary recommendations first; platform/build issues such as missing runtime tools can look like task-quality failures.
- In the difficulty artifact's per-test table, look for tests with `0 / 10` successful runs. At least one agent run should pass each individual test somewhere across the evaluation set.
- If a `0 / 10` test encodes an unreasonable hidden requirement, either clarify the instruction and supporting docs or remove/reframe that test.

## Build Completion Timeout / Verifier Did Not Run

- Build-completion timeouts can be platform noise, but do not assume that until the exact artifact is inspected.
- First check `task.toml` resource/timeouts, Docker build behavior, and whether verifier dependencies are available offline.
- `verifier_did_not_run` often means `tests/test.sh`, reward writing, runtime dependencies, or environment startup failed before pytest could run.
- Always inspect downloaded artifacts for logs before revising blindly.
