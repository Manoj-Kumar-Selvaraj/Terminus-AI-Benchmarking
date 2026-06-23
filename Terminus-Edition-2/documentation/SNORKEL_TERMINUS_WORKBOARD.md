# Snorkel Terminus Workboard

Last updated: 2026-05-28

## Operating Rules

- Treat Snorkel reviewer comments and agent-review weaknesses as the repair contract.
- Read the current files before changing anything; reviewer feedback may describe an older zip.
- Use [SNORKEL_DISCUSSION_NOTES.md](SNORKEL_DISCUSSION_NOTES.md) for live field notes that clarify or supersede older documentation, especially verifier dependency handling.
- Do not start new multi-container or UI-building tasks unless a later project announcement reopens them; existing pipeline/revision tasks are grandfathered.
- Keep milestone instructions cumulative and self-contained.
- Use absolute `/app/...` paths in task instructions.
- Spell out literal on-disk status strings and distinguish input status columns from output status columns.
- Every stated behavior needs a behavioral test, and every test function needs a useful docstring.
- Tests should overwrite input CSVs at runtime, not rely on shipped fixture values.
- `task.toml` should use Edition 2 metadata, no `id`, no root `[agent]` or `[verifier]`, and `number_of_milestones` must match `[[steps]]`.
- `task.toml` must include `allow_internet = false` under `[environment]`.
- Dockerfiles must not copy `steps/`, `tests/`, or `solution/`.
- Every `test.sh` must always write `/logs/verifier/reward.txt` and preserve the pytest exit status. It must not install or download runtime dependencies; bake verifier dependencies into `environment/Dockerfile`.
- Rubrics must use one line per criterion: `Agent ..., +1/+2/+3/+5/-1/-2/-3/-5`; include at least three negatives and no meta references to tests, oracle, NOP, or task files.
- Zip from inside the task folder so `task.toml`, `environment/`, and `steps/` are at archive root.

## Current Queue

| Priority | Task | Current evidence | Next action |
|---|---|---|---|
| P0 | `New-Cobol-Tasks/*` | Five new COBOL tasks generated with digest-pinned Dockerfiles, offline verifier deps, `.dockerignore`, paste-ready rubrics, and clean root zips. Docker oracle checks pass for all five; NOP-style runs fail as expected. | Ready for static/difficulty submission runs. |
| P0 | `go-event-ticket-refund-matcher` | Latest local validation shows oracle `1.0` and NOP `0.0`; repackaged fixed zip and paste-ready rubric now exist in `Revision-Fixed/`; zip excludes `rubric.txt`. | Ready for Snorkel upload/resubmission. |
| P0 | `go-invoice-payment-reconciliation` | Reviewer requested rubric criteria to start with `Agent`; fixed rubric now has 30 compliant lines, 7 negatives, and valid scores. Follow-up static log showed unpinned Go base image; fixed zip now has a digest-pinned Dockerfile and `environment/.dockerignore`; Docker build smoke test passed. | Ready for Snorkel upload/resubmission. |
| P0 | `go-fitness-class-refund-matcher` | Fixed zip and rubric exist in `Revision-Fixed/`; latest local validation shows oracle `1.0` and NOP `0.0`; difficulty artifact says hard with 20% success per frontier model after the spec fixes. | Ready for Snorkel upload/resubmission after one final zip-root and rubric-format check. |
| P1 | `ruby-auto-service-invoice-rebate-matcher` | Latest submission zip exists; latest local oracle is `1.0`; older NOP was `0.0`, but no latest NOP run found after the final zip timestamp. | Run NOP on latest task/zip, then create/sync rubric text and move final zip/rubric into `Revision-Fixed/` if this is a revision deliverable. |
| P1 | `go-transit-fare-rebate-matcher` | Latest submission zip exists; latest local oracle is `1.0`; no latest NOP evidence found in logs. | Run NOP, review rubric sync, then package into `Revision-Fixed/` if needed. |
| P1 | `ruby-campus-meal-plan-credit-matcher` | Latest submission zip exists; latest local oracle is `1.0`; no latest NOP evidence found in logs. | Run NOP, review rubric sync, then package into `Revision-Fixed/` if needed. |
| P2 | Recently modified tasks: `go-parking-citation-credit-matcher`, `go-library-loan-waiver-matcher`, `go-veterinary-visit-credit-matcher`, `go-dental-claim-credit-matcher`, `go-saas-license-rebate-matcher` | Recent task directories and submission zips exist; validation state not checked in this pass. | Audit each against the final gate before uploading or revising. |
| P2 | Existing fixed revision bundle: event, logistics, conference, waterpark | Fixed artifacts already exist in `Revision-Fixed/`; some have rubric text, some do not. | Confirm which ones are already uploaded; add missing rubric files if platform needs paste-ready rubrics. |

## Fitness Revision Notes

The difficulty reports identified these core spec traps and the current task appears to have addressed them:

- `BOOKED` is the on-disk literal for posted class status; do not remap it to `POSTED`.
- Output `status` must remain `MATCHED` or `UNMATCHED`; it must never contain input booking values like `BOOKED`.
- Milestone 3 date gating must be explicit about whether absent date columns skip date validation or present-but-empty dates are ineligible.

## Final Gate For Any Task

- [ ] Read `task.toml`, `environment/Dockerfile`, every milestone `instruction.md`, `tests/test.sh`, `tests/test_mN.py`, `solution/solve.sh`, `solution/solveN.sh`, and the edited source files.
- [ ] Confirm `[environment]` includes `allow_internet = false`.
- [ ] Confirm `test.sh` does not run `apt-get install`, `pip install`, `curl`, `uv` installs, `npm install`, or other runtime dependency downloads.
- [ ] Confirm verifier dependencies needed by `test.sh` are already baked into `environment/Dockerfile`.
- [ ] Confirm each milestone instruction states every behavior tested at that milestone.
- [ ] Confirm each test mutates inputs, checks behavior, and has a docstring.
- [ ] Confirm oracle solves by fixing/running program logic, not writing final answers.
- [ ] Confirm local oracle mean is `1.0`.
- [ ] Confirm local NOP mean is `0.0`.
- [ ] Confirm rubric is current, has at least three negatives, uses only valid scores, and has no forbidden meta references.
- [ ] Confirm the submission zip does not include local rubric helper files such as `rubrics.txt`; keep paste-ready rubrics outside the zip.
- [ ] Create or refresh the final zip from inside the task directory.
- [ ] List the zip and verify root entries are task files directly, not a wrapper folder.
- [ ] Put fixed zip plus paste-ready rubric in `Revision-Fixed/` for revision submissions.

## Helpful Commands

```powershell
stb harbor run -a oracle --path .\TASK_NAME -q --yes
stb harbor run -a nop --path .\TASK_NAME -q --yes
tar -tf .\Revision-Fixed\TASK_ZIP.zip | Select-Object -First 20
Select-String -Path .\Revision-Fixed\TASK_RUBRIC.txt -Pattern '^Agent .+, [+-](1|2|3|5)$' -NotMatch
```
