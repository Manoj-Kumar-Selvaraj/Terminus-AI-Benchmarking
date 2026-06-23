# Tolerance Profiles

`tolerance_key` labels which numeric slack policy applies when comparing serialized payloads. Common registry entries:

| Key | Meaning |
|-----|---------|
| `FED` | Federal wire schema — exact match |
| `ACH` | ACH batch schema — exact match |
| `SWIFT` | SWIFT MT schema — exact match |

Producer feeds sometimes ship abbreviated segment codes (`f`, `a`, `s`) that normalize to the canonical segment ids configured in `ALIAS_*` rules.
