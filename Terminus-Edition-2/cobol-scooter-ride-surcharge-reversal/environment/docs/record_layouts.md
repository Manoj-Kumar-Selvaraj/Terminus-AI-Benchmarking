# Fixed-Width Layouts

Source: type 1, record_id 12, account 8, zone_code 3, amount 10, source_date 8, status 1, branch 4.

Action: type 1, record_id 12, account 8, zone_code 3, amount 10, action_date 8, reason 3, branch 4.

Record id and account fields are space-padded in the fixed-width files and must be trimmed only for CSV output and equality comparison. Amount fields are 10-character zero-padded cent strings and the report preserves the action amount text verbatim.
