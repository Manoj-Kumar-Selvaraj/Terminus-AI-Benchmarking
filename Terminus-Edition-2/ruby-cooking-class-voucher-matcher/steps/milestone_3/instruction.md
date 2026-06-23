Extend `/app/lib/reconcile.rb` for dated voucher batches. `classes.csv` may include `class_date` and `vouchers.csv` may include `voucher_date`. If both files still use the earlier schemas without those columns, keep the prior matching behavior. A voucher can match only when all prior criteria still pass, `voucher_date` is listed as `open` in `/app/config/cutoff_calendar.txt`, and `voucher_date` is not later than the class `class_date`. Missing, closed, or unlisted `voucher_date` values are not eligible. A class with missing `class_date` is not eligible.

Treat calendar `open` state case-insensitively after trimming whitespace. Skip malformed calendar lines silently rather than treating them as open dates. Each valid calendar row is a date token followed by a state token; rows that do not parse into exactly those two tokens are ignored.

If multiple unused class rows match one voucher, choose the row with the latest `class_date`; if dates tie, choose the earliest class input row. Consumption is by row position, not `class_id`, so duplicate ids in separate rows remain separate. Keep aliases from milestone 2 and keep the existing report and summary schemas.

Continue to write `/app/out/voucher_report.csv` and `/app/out/voucher_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
