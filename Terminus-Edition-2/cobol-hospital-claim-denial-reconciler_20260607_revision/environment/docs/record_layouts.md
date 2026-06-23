# Fixed-Width Layouts

Each physical line begins with a one-byte record type prefix: `S` for source (claim) rows and `A` for action (denial) rows. The type byte is separate from `record_id` and must not be included in matching or report output.

Source (bytes after the type prefix): record_id 12, account 8, service 3, amount 10, source_date 8, status 1, branch 4.

Action (bytes after the type prefix): record_id 12, account 8, service 3, amount 10, action_date 8, reason 3, branch 4.

Fixed-width fields may contain trailing spaces in the input files. Comparisons and CSV output use trimmed logical values: `record_id` and `account` exclude the type prefix and are written without fixed-width padding or trailing spaces. The verifier compares report CSV fields exactly against these trimmed logical values.
