# Batch operations

The spa finance team runs reconciliation from `/app` after the nightly export lands.

```bash
/app/scripts/run_batch.sh
```

`run_batch.sh` executes `/app/lib/reconcile.rb` with Ruby 3.3. The script assumes:

- Input feeds exist at `/app/data/appointments.csv` and `/app/data/refunds.csv`
- Output directory `/app/out/` is writable
- Config files, when referenced by the reconciler version in use, live under `/app/config/`

The batch is idempotent: re-running against the same inputs must replace prior outputs rather
than append to them. Operations reruns the batch after code fixes without manual cleanup.
