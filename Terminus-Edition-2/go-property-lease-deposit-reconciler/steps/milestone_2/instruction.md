Extend channel normalization to support legacy values on both lease and deposit rows. After trimming and case folding, map `CC` to `CARD` and `WIR` to `WIRE`. Matched report rows must emit only canonical channels (`ACH`, `CARD`, or `WIRE`); unmatched rows still leave `channel` blank.

Preserve full identifier, customer, amount, status, and channel matching, one-time lease-row consumption, deposit input order, the existing report schema, and positive summary cents.
