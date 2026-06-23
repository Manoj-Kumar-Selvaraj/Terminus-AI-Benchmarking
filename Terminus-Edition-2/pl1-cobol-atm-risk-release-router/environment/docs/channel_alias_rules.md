# Channel Alias Rules (Milestone 2)

Alias declarations use `raw=>canonical` form (for example `ATM=>CASH`).

Both hold and release channel values must be trimmed, case-folded, and mapped through the alias table before comparison. The raw alias key may appear on either side in any letter case or with surrounding whitespace.

After normalization, the two canonical channel values must agree. Matched report rows emit the canonical channel value only. Unknown channels remain unmatched.
