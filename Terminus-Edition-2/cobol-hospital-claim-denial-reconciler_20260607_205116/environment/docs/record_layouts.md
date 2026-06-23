# Fixed-Width Layouts

Each physical line begins with a one-byte record type prefix: `S` for source (claim) rows and `A` for action (denial) rows. The type byte is separate from `record_id` and must not be included in matching or report output.

Source (bytes after the type prefix): record_id 12, account 8, service 3, amount 10, source_date 8, status 1, branch 4.

Action (bytes after the type prefix): record_id 12, account 8, service 3, amount 10, action_date 8, reason 3, branch 4.

The compliance feed appends fields after the original layouts:

- Source suffix: hospital_code 5, state_code 2, supporting_documents_validated 1.
- Action suffix: hospital_code 5, state_code 2.

The OFAC file `/app/config/ofac_screening.dat` is fixed-width without a type prefix:
account 8, hospital_code 5, decision 5, screen_date 8. Decisions are `CLEAR`, `HOLD`, or `BLOCK`.

Legacy text fields may be padded with either spaces or binary low-values (`X'00'`). Low-values are padding only in textual fields. A low-value in an amount or date makes that record ineligible.

Fixed-width fields may contain trailing spaces in the input files. Comparisons and CSV output use trimmed logical values: `record_id` and `account` exclude the type prefix and are written without fixed-width padding or trailing spaces. The verifier compares report CSV fields exactly against these trimmed logical values.
