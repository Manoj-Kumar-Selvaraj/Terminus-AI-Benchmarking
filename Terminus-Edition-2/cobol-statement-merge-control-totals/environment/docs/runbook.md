# Merge runbook

## Purpose

The `stmt_merge` batch merges nightly statement sort runs listed in
`/app/config/stream_manifest.txt` into account/date control totals at
`/app/out/control_totals.dat`.

## Build and run

```bash
/app/scripts/run_batch.sh
```

Compilation uses GnuCOBOL free format:

```bash
cobc -x -free -o /app/build/batch /app/src/stmt_merge.cbl
```

## Commit boundaries

`/app/config/job.properties` defines:

- `commit_cycle` — cycle date stamped on committed control rows
- `commit_every` — flush a checkpoint after this many statement rows

Checkpoints are written to `/app/out/checkpoint.dat`. A restart after ABEND must
resume using the last checkpoint without duplicating committed totals or dropping
pending accumulator state.

## ABEND testing

Set `STMT_MERGE_ABEND_AFTER` to a positive integer to stop the batch after that
many statement rows (simulated ABEND). Clear outputs except the checkpoint, then
set `STMT_MERGE_RESTART=1` and rerun to validate restart behavior.

## Evidence

See `/app/evidence/batch_incident.log` and `/app/docs/incident_timeline.md` for
the production divergence that triggered this review.
