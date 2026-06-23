# Orbit Downlink Frame Auditor

The PL/I-style batch reconciles `/app/data/audits.psv` against `/app/data/catalog.psv`, validates pass-window eligibility, and, in later milestones, audits downlink replay state under `/app/spool/` and `/app/state/`.

Policy constants live in `/app/src/audit_rules.pli`. Runtime switches are `%SET` directives in `/app/src/audit_batch.pli`. Run:

```bash
/app/scripts/run_batch.sh
```

## Static audit outputs

See `/app/docs/audit_report_schema.md` and `/app/docs/audit_summary_contract.md`.

## Replay, sequence, and station outputs

See:

- `/app/docs/replay_recovery_contract.md`
- `/app/docs/sequence_contract.md`
- `/app/docs/station_integrity_contract.md`
