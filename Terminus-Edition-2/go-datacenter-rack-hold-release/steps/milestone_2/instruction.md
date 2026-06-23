Extend the rack hold release reconciler under `/app` while preserving every milestone 1 matching, consumption, report, and summary rule.

Milestone 2 adds runtime `access_tier` aliases from `/app/config/access_tier_aliases.csv`. The file has `alias,canonical` columns; after trimming and case folding, accept only rows whose canonical target is exactly `HOT`, `WARM`, or `COLD`. Ignore malformed rows, unknown canonical targets, and alias cycles. Canonical input values `HOT`, `WARM`, and `COLD` remain valid even if the alias file is empty. The alias file may be overwritten between runs. Normalize source and correction `access_tier` values before matching, validate the normalized value through the same matching gates, and emit only canonical `access_tier` values in matched report rows. Unknown normalized values stay unmatched even if both sides share the same unknown value.

Amounts are part of the identity gate. Treat `amount` as a canonical positive integer string after trimming: `1` through `999999999` are valid, while `0`, negatives, signs such as `+10`, leading-zero forms such as `010` or `0104`, decimals, blanks, and non-numeric values are ineligible. A source and correction can match only when both amount fields are valid canonical positive integer strings and the strings are equal. Summary totals must add only valid canonical integer amounts; invalid unmatched correction amounts contribute `0` to `unmatched_amount`.

Continue to ignore `/app/config/windows.csv` for matching. Keep the report columns, correction input order, exact `MATCHED` and `UNMATCHED` labels, blank unmatched `access_tier` behavior, and summary key names from milestone 1.

Keep the deliverable as a Go CLI compiled from the source under `/app` with `/usr/local/go/bin/go`.
