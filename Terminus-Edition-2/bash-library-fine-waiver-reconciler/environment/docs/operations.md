# Operations

Batch entrypoint: `/app/scripts/reconcile.sh`.

Inputs:
- `/app/data/fines.csv`
- `/app/data/waivers.csv`

Config:
- `/app/config/cutoff_calendar.txt` — open/closed calendar days
- `/app/config/channels.csv` — enabled desk channels (later milestones)

Outputs:
- `/app/out/waiver_report.csv`
- `/app/out/waiver_summary.json`

Working directory must be `/app` (`WORKDIR` in the container image).
