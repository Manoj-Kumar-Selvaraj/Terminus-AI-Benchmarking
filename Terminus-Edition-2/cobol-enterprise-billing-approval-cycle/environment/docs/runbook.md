# Enterprise billing approval runbook

Build and run the batch with:

```bash
/app/scripts/run_batch.sh
```

Compilation uses:

```bash
cobc -x -free -I /app/copybooks -o /app/build/batch /app/src/billing_approval.cbl
```

`/app/config/usage_manifest.txt` lists usage files in processing order. `/app/config/approval_matrix.txt` supplies `regional_cents` and `dual_cents` thresholds. `/app/config/prior_ledger.dat` contains account/batch combinations already billed in earlier runs.

Restart testing uses `BILLING_ABEND_AFTER=<rows>` to simulate an ABEND and `BILLING_RESTART=1` to resume from `/app/out/checkpoint.dat`.
