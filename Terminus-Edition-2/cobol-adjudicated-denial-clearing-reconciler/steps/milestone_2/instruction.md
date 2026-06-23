Add legacy service aliases on the action side only. After trimming and case folding, map `E1` to `ER`, `LB` to `LAB`, and `XR` to `IMG`. Source-side services must remain canonical (`ER`, `LAB`, or `IMG`); alias spellings on source rows stay ineligible. Normalize action services before matching, then apply the same milestone 1 gates. Matched rows report the canonical source service; unmatched rows leave `service` blank.

Keep milestone 1 parsing, consumption, report schema, `MATCHED`/`UNMATCHED` labels, action reasons on every row, and positive summary cents unchanged.
