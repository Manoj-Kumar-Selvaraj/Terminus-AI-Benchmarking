# Legacy service codes

Property-management and POS integrations do not always emit canonical service area names.
Short codes such as `MSG`, `FAC`, or `SAU` may appear in appointment or refund exports.

Deployments that support runtime alias resolution load `/app/config/service_aliases.csv`.
That file maps alias tokens to canonical service areas and may include an `enabled` flag per
row. When the alias file is absent, reconciliation falls back to exact canonical names only.

Alias tables are maintained by operations, not by the nightly export job. Changes take effect
on the next batch run without redeploying appointment history.
