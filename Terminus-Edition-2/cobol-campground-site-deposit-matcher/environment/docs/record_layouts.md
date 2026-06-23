# Fixed-Width Layouts

The source file is `/app/data/site_fees.dat`. Each source line has these fixed positions:

- byte 1: record type, normally `S`
- bytes 2-13: `record_id`, 12 characters, trim surrounding spaces for comparisons and CSV output
- bytes 14-21: `account`, 8 characters, trim surrounding spaces for comparisons and CSV output
- bytes 22-24: `site_class`, 3 characters, trim and uppercase before canonical comparison
- bytes 25-34: `amount_cents`, 10 characters; valid amounts are positive base-10 digits only
- bytes 35-42: `source_date`, 8 digits in `YYYYMMDD` text form
- byte 43: `status`, where only `G` is eligible
- bytes 44-47: `branch`, 4 characters, trim for comparisons and CSV output

The action file is `/app/data/deposit_returns.dat`. Each action line has these fixed positions:

- byte 1: record type, normally `A`
- bytes 2-13: `record_id`, 12 characters
- bytes 14-21: `account`, 8 characters
- bytes 22-24: `site_class`, 3 characters
- bytes 25-34: `amount_cents`, 10 characters; preserve the trimmed action text in the report
- bytes 35-42: `action_date`, 8 digits in `YYYYMMDD` text form
- bytes 43-45: `reason`, 3 characters
- bytes 46-49: `branch`, 4 characters

The output report is `/app/out/camp_deposit_report.csv` with header `record_id,account,site_class,amount_cents,reason,status`.
The output summary is `/app/out/camp_deposit_summary.txt` with integer `key=value` lines for `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`.
