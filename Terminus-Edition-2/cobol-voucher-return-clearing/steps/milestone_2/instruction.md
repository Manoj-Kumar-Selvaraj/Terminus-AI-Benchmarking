One more production case is still wrong: duplicate return rows are consuming the same settled voucher more than once. Finish the `/app` batch so each settled voucher can clear at most one return while keeping the milestone 1 behavior intact.

Keep `/app/out/voucher_return_report.csv` in return-file order with schema `voucher_id,account_id,reason,amount_cents,status`. Keep `/app/out/voucher_return_summary.txt` as `key=value` lines for `cleared_count`, `cleared_amount_cents`, `exception_count`, and `exception_amount_cents`, with cleared and exception amounts reported as positive cents.
