Nightly invoice batch jobs fail before publishing ledger output. Event logs show `Forbidden` responses while the job container reads its billing configuration. Review `/app/evidence/forbidden_trace.log`, `/app/docs/rbac_contract.md`, `/app/docs/batch_contract.md`, and the manifest bundle under `/app/manifests`.

Restore successful configuration reads for the batch service account without changing the publication contract. The CronJob identity must match the RoleBinding subject in `billing-batch`.

The ConfigMap lists multiple billing windows, but the nightly batch must publish for the window pinned by `active_window_key` (currently `current_window`). Do not rely on list order in `windows.yaml`; the overlap fixture expects active window `WIN-20260612` and ledger artifact `ledger-WIN-20260612`.

The offline simulator at `/app/scripts/run_simulation.sh` evaluates authorization and window selection against the manifest bundle.
