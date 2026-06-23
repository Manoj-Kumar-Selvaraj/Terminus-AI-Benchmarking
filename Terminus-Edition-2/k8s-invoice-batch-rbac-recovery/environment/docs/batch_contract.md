# Invoice Nightly Batch Contract

The finance platform runs `invoice-nightly-batch` in namespace `billing-batch`.

Each successful run must:

1. Read `invoice-batch-config` to determine the active billing window.
2. Publish exactly one ledger artifact for that billing window.
3. Name ledger artifacts with the `ledger_prefix` from the ConfigMap plus the `window_id`.

## Active billing window resolution

`invoice-batch-config` carries multiple candidate windows in `windows.yaml`, but the nightly batch must not assume the first listed window is active.

Resolution order used by the offline simulator:

1. **Pinned window** — read the ConfigMap data key named by `active_window_key` (default `current_window`). When present, that value is the authoritative `window_id`.
2. **Timestamp match** — if no pin exists, select the window whose `open_ts` and `close_ts` bracket the batch run timestamp from `/app/sim/config.json`.
3. **First listed** — only when neither pin nor timestamp match applies, the first `window_id` entry in `windows.yaml` is used.

The overlap fixture expects billing window `WIN-20260612` and ledger artifact `ledger-WIN-20260612`.

The batch container identity is the CronJob pod service account. Configuration reads and ledger publication must succeed under that identity chain.
