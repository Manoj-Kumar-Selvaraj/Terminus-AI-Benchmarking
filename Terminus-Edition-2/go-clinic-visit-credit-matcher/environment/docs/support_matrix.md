# Support Matrix

Allowed credit channels are `ACH`, `CARD`, and `WIRE`. Runtime eligibility is controlled by `/app/config/methods.csv`, which uses `channel,enabled` rows. Channel names and `enabled` values are interpreted case-insensitively after trimming surrounding whitespace. A canonical channel is eligible only when it has an enabled value of `true`; missing, disabled, malformed, blank, or non-true rows are treated as ineligible.
