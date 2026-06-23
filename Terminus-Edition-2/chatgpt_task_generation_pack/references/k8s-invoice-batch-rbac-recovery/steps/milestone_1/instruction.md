Nightly invoice batch jobs fail before publishing ledger output. Event logs show `Forbidden` responses while the job container reads its billing configuration. Review `/app/evidence/forbidden_trace.log`, `/app/docs/rbac_contract.md`, and the manifest bundle under `/app/manifests`.

Restore successful configuration reads for the batch service account without changing the publication contract. The offline simulator at `/app/scripts/run_simulation.sh` evaluates authorization against the manifest bundle.
