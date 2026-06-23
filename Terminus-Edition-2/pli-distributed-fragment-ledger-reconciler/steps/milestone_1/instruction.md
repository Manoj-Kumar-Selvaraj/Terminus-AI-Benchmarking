The distributed fragment PL/I reconciler orphans valid merges. Fix `/app/src/fragment_batch.pli`, `/app/src/fragment_rules.pli`, or the batch harness so `/app/data/merges.psv` links against `/app/data/fragments.psv`.

Milestone 1 requires full agreement on `fragment_id`, `parent_id`, `shard_value`, `channel`, and `ingest_class`, fragment `state` equal to `ELIGIBLE_STATE`, and `opcode` one of `OPCODE_1`, `OPCODE_2`, or `OPCODE_3`. Each fragment row may be consumed once. Preserve merge order. Write `/app/out/fragment_report.csv` and `/app/out/fragment_summary.txt`.

Status must be exactly `LINKED` or `ORPHAN`.
