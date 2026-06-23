Load pass tier aliases from `/app/config/kind_aliases.csv` in `/app/app/reconcile.rb` instead of hardcoded mappings. The file has columns `alias` and `canonical`; trim and uppercase both columns, use first-row-wins for duplicate aliases, and leave unlisted codes as trimmed uppercase literals. Keep all prior matching, window, timestamp, consumption, tie-break, output schema, and positive summary rules.

After alias lookup, session and correction canonical `pass_tier` values must match for a row to qualify; eligible canonical tiers remain `DAY`, `SEASON`, and `VIP`. Matched rows emit the canonical session `pass_tier`; unmatched rows leave `pass_tier` blank. Continue writing `/app/out/lift_gate_release_report.csv` and `/app/out/lift_gate_release_summary.txt` with the same header, `MATCHED`/`UNMATCHED` status values, correction order, and summary keys as before.

Input files remain `/app/data/lift_sessions.csv`, `/app/data/gate_releases.csv`, and `/app/config/windows.csv`.
