# Recreate Submission Zips

This folder contains scripts to regenerate zips with deterministic names.

- Output naming is always `<task-name>.zip`
- Existing zip is deleted before re-creation
- Archive layout is root-correct for Linux CI

## Scripts

- `recreate_all.sh`: recreate all tasks listed in `tasks.txt`
- `recreate_one.sh`: recreate one task zip
- `tasks.txt`: default list of tasks

## Examples

```bash
bash scripts/recreate_zips/recreate_all.sh
bash scripts/recreate_zips/recreate_one.sh aws-lambda-event-source-mapping-recovery
```