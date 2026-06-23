# Invoice Nightly Batch Contract

The finance platform runs `invoice-nightly-batch` in namespace `billing-batch`.

Each successful run must:

1. Read `invoice-batch-config` to determine the active billing window.
2. Publish exactly one ledger artifact for that billing window.
3. Name ledger artifacts with the `ledger_prefix` from the ConfigMap plus the `window_id`.

The batch container identity is the CronJob pod service account. Configuration reads and ledger publication must succeed under that identity chain.
