# Record Layouts

`/app/data/accessions.csv` has `sample_id,patient_id,chain_id,kind,amount,source_ts,status,location`.
`/app/data/reassignments.csv` has `action_id,sample_id,patient_id,chain_id,kind,amount,action_ts,reason,location`.
`/app/config/kind_aliases.csv` has `alias,canonical` rows used by the later alias-aware reconciliation rule.
`/app/config/windows.csv` has `chain_id,open_ts,close_ts,state` rows used by the realtime-window rule.

Timestamps are compact UTC values in `YYYYMMDDHHMMSS` form. Amounts are positive base-10 integers.
`/app/config/reasons.csv` has `reason,eligible` rows used by the data-driven reason gate in the final realtime-window milestone.
