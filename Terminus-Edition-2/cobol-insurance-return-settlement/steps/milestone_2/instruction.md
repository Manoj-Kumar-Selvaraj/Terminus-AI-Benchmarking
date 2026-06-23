One more production case is still wrong: duplicate return rows are consuming the same settled wire more than once. Finish the `/app` batch so each settled wire can clear at most one return while keeping the milestone 1 behavior intact.

Keep `/app/out/wire_return_report.csv` in return-file order with schema `wire_id,account_id,reason,amount_cents,status`. Keep `/app/out/wire_return_summary.txt` as `key=value` lines for `cleared_count`, `cleared_amount_cents`, `exception_count`, and `exception_amount_cents`, with cleared and exception amounts reported as positive cents.
