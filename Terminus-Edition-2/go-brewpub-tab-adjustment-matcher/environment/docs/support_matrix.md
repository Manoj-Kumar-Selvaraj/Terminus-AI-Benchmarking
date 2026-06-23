# Support matrix

## Pour tier aliases

| Alias | Canonical | Notes |
|-------|-----------|-------|
| PT | PINT | Case-insensitive after trimming |
| PC | PITCH | Case-insensitive after trimming |
| KG | KEG | Case-insensitive after trimming |

Allowed canonical pour_tier values are PINT, PITCH, and KEG.

## Adjustment method gating

When adjustment method gating is enabled, `/app/config/methods.csv` uses `method,enabled`. A method is eligible only when `enabled` trims and case-folds to `true`; disabled, missing, blank, and malformed rows are not eligible.
