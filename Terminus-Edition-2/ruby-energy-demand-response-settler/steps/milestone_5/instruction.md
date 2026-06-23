Fix `/app/app/reconcile.rb` while preserving all milestone 1 through 4 behavior from `/app/docs/reconciliation_contract.md`.

Add milestone 5 operator overrides from `/app/config/settlement_overrides.csv`. Valid `DENY` overrides block a settlement before source selection, and valid `FORCE_RESOURCE` overrides change only the settlement's effective resource type before the normal candidate, policy, budget, and consumption rules run.
