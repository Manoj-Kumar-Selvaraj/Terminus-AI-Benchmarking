# Task list index (2026-06-02)

Three root-level lists track the Edition 2 corpus:

| File | Count | Purpose |
|------|-------|---------|
| `old_tasks.txt` | 123 | Catalog of established / previously tracked tasks, including all revision tasks absorbed on 2026-06-01 |
| `revision_tasks.txt` | 11 | Active v3 revision intake; previous revision backlog was absorbed into `old_tasks.txt` |
| `new_tasks.txt` | 43 | New task batch kept separate from old/revision catalogs |

## Folders

- `new-tasks/tasks.txt` - initial 18-name batch input, superseded by newer `new_tasks.txt` additions
- `new-tasks-v5/llmaj-reports/` - strict LLMaJ reports for the current new-task hardening pass
- `new-tasks-v5/batch-1/` - packaged first two LLMaJ-hardened tasks
- `reworked-tasks/reworked_tasks.txt` - cleared after syncing into `old_tasks.txt`
- `reworked-tasks-v2/revised_tasks.txt` - cleared after syncing into `old_tasks.txt`
- `reworked-tasks-v3/revised_tasks.txt` - mirrors active v3 revision intake

## Strict LLMaJ (new batch)

```powershell
python scripts/fix_llmaj_test_deps.py new_tasks.txt
python scripts/fix_llmaj_new_tasks.py
python scripts/run_llmaj_new_tasks_batch.py
python scripts/summarize_llmaj_reports.py
```

Reports: `new-tasks-v5/llmaj-reports/<task>_strict_llmaj.json` for the current new-task pass, or `reworked-tasks-v2/llmaj-reports/<task>_strict_llmaj.json` for older rework batches.

Expected structural noise: `anti_cheating_measures` (oracle `steps/*/solution/` exists locally).

