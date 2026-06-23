The orbit downlink frame PL/I auditor is rejecting valid catalog matches and accepting some invalid comparisons after a control-deck refresh. Restore the end-of-pass audit behavior for `/app/data/audits.psv` against `/app/data/catalog.psv` while preserving the existing operator command:

```bash
/app/scripts/run_batch.sh
```

The operator notes in `/app/evidence/` include unrelated receiver and dashboard warnings. Treat them as context only; the required behavior is defined below.

## Input formats

`/app/data/catalog.psv` is pipe-delimited with this header:

```text
frame_id|craft_id|channel|payload_hash|recv_ts|state|service_class
```

`/app/data/audits.psv` is pipe-delimited with this header:

```text
audit_id|frame_id|craft_id|channel|payload_hash|audit_ts|verdict_code|service_class
```

`/app/src/audit_rules.pli` contains PL/I-style declarations. The auditor must read these declarations at runtime:

```text
ELIGIBLE_STATE
VERDICT_A
VERDICT_B
VERDICT_C
ALIAS_*
```

Alias declarations use `raw=>canonical`. Alias keys and values may include case or surrounding whitespace differences. Aliases apply to `craft_id`, `channel`, and `service_class` on both catalog and audit sides before comparison.

## Required output formats

`/app/out/audit_report.csv` must be pipe-delimited with this exact header:

```text
audit_id|frame_id|craft_id|channel|service_class|payload_hash|verdict_code|status
```

`status` must be exactly `ACCEPTED` or `REJECTED`. The report must contain one row for every audit input row in the same order. Accepted rows must emit the canonical matched catalog `service_class`; rejected rows must leave `service_class` blank.

`/app/out/audit_summary.txt` must contain exactly these four key-value lines in this order:

```text
matched_count=<integer>
matched_frames=<integer>
rejected_count=<integer>
rejected_frames=<integer>
```

`/app/out/catalog_consumption.psv` must be pipe-delimited with this exact header:

```text
audit_id|catalog_row|recv_ts|frame_id
```

Write one row for each accepted audit, in audit order. `catalog_row` is the zero-based physical data-row position in `/app/data/catalog.psv`; the header is not counted. Record the selected catalog row's `recv_ts` and `frame_id`. Rejected audits do not appear in this trace.

## Requirements

1. Compare the full `frame_id`; prefix-only matches are not valid.
2. Compare canonicalized `craft_id`.
3. Compare canonicalized `channel`.
4. Compare `payload_hash` exactly.
5. Compare canonicalized `service_class`.
6. Load `ELIGIBLE_STATE` from `/app/src/audit_rules.pli` at runtime.
7. Load `VERDICT_A`, `VERDICT_B`, and `VERDICT_C` from `/app/src/audit_rules.pli` at runtime.
8. Treat verdict comparisons case-insensitively.
9. Apply `ALIAS_*` declarations to catalog rows.
10. Apply `ALIAS_*` declarations to audit rows.
11. Trim and case-fold alias lookup keys.
12. Preserve audit input order in `/app/out/audit_report.csv`.
13. Consume each catalog data row at most once.
14. Reject a second audit that attempts to use an already consumed catalog row.
15. When multiple unused catalog rows qualify for one audit, select the row with the latest `recv_ts`.
16. When multiple qualifying rows have equal `recv_ts`, select the earliest catalog data row.
17. Emit canonical `service_class` only for accepted rows.
18. Leave `service_class` blank for rejected rows.
19. Preserve the exact report and summary schemas.
20. Regenerate the catalog consumption trace from the selected physical rows.
21. Ignore `/app/config/pass_windows.psv` for this initial repair.

## Verifier coverage stated as requirements

The verifier will check all of these externally visible behaviors: valid full-key acceptance, prefix-only frame rejection, craft mismatch rejection, channel mismatch rejection, payload mismatch rejection, service-class mismatch rejection, ineligible catalog state rejection, unknown verdict rejection, case-insensitive verdict acceptance, catalog-side craft aliasing, audit-side craft aliasing, channel aliasing, service-class aliasing, whitespace-padded alias declarations, consume-once rejection, latest receive timestamp selection, equal receive timestamp tie-breaking, physical-row consumption trace accuracy, report order preservation, summary/report count agreement, and unchanged output headers.

Do not remove the public input files, output files, command path, or documented schemas.
