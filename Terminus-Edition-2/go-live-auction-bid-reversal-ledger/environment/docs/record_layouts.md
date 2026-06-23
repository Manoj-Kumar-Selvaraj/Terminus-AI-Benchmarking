# Record Layouts

`/app/data/bids.csv` contains bid candidates. `/app/data/reversals.csv` contains realtime reversal events. Both files use string identifiers; ids must be compared by full equality after trimming.

`/app/config/session_windows.csv` has `session_id,open_ts,close_ts,state`. `state` values are compared case-insensitively.

`/app/config/channel_aliases.csv` has `alias,canonical`. Later rows can replace earlier alias mappings.

`/app/config/reversal_reasons.csv` has `reason,eligible`. Later rows can replace earlier reason eligibility.
