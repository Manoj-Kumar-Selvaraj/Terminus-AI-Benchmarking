The merge now ABENDs during checkpoint windows and a rerun doubles committed debits before operators halt the job. Evidence shows restart ignored `/app/out/checkpoint.dat` and replayed already committed statement rows.

Restore restart handling so `STMT_MERGE_RESTART=1` resumes after the last checkpoint without double-counting or skipping pending totals. A restart run must read `/app/out/checkpoint.dat` from the prior ABEND; if the checkpoint is missing or unreadable, exit with a non-zero status instead of silently reprocessing from the beginning. Resume using the checkpoint file and record position fields (`CKPT-FILE-NUM`, `CKPT-RECORD-NUM`) so multi-file manifests continue at the correct stream.

Keep milestones 1–3 behavior, ABEND simulation via `STMT_MERGE_ABEND_AFTER`, and all documented output contracts.
