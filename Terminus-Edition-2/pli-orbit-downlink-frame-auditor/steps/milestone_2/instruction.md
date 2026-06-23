The baseline orbit downlink frame auditor behavior must now be pass-window aware. Operations report that frames outside valid contact windows are still appearing as accepted, while unrelated receiver warnings in `/app/evidence/` have made the incident triage noisy. Preserve the existing audit behavior and enforce the pass-window contract.

Run command remains:

```bash
/app/scripts/run_batch.sh
```

## Existing input and output formats

The existing catalog, audit, rule-deck, report, summary, and consumption-trace formats remain unchanged.

## Additional input format

`/app/config/pass_windows.psv` is pipe-delimited. The default file uses this header:

```text
craft_id|open_ts|close_ts|state
```

Verifier fixtures may include an additional `channel` column. When present, the channel must also match after canonicalization.

Timestamps are 14-digit UTC strings in `YYYYMMDDHHMMSS` form.

The open pass state is declared in `/app/src/audit_rules.pli` as:

```text
OPEN_PASS_STATE
```

## Required output formats

`/app/out/audit_report.csv`, `/app/out/audit_summary.txt`, and `/app/out/catalog_consumption.psv` must keep their exact existing schemas.

## Requirements

1. Preserve every existing audit requirement.
2. Load `OPEN_PASS_STATE` from `/app/src/audit_rules.pli` at runtime.
3. Use canonical craft values for pass-window lookup.
4. Use canonical channel values for pass-window lookup when the pass-window file has a channel column.
5. Require a matching open pass window for accepted catalog frames.
6. Require `open_ts <= recv_ts <= close_ts`.
7. Require `recv_ts <= audit_ts <= close_ts`.
8. Reject closed pass windows.
9. Reject missing pass windows.
10. Reject unlisted craft/channel pass windows.
11. Reject malformed pass-window rows.
12. Reject malformed catalog `recv_ts` values.
13. Reject malformed audit `audit_ts` values.
14. Preserve consume-once behavior under pass-window validation.
15. Preserve latest-`recv_ts` candidate selection under pass-window validation.
16. Preserve equal-timestamp tie-breaking under pass-window validation.
17. Preserve alias normalization under pass-window validation.
18. Preserve the report and summary schemas.

## Verifier coverage stated as requirements

The verifier will check all of these externally visible behaviors: valid audit inside an open pass window, catalog receive before pass open rejection, catalog receive after pass close rejection, audit timestamp before receive timestamp rejection, audit timestamp after pass close rejection, closed-window rejection, missing-window rejection, unlisted craft/channel rejection, malformed pass-window tolerance, malformed `recv_ts` rejection, malformed `audit_ts` rejection, aliasing before window lookup, consume-once behavior with windows, latest receive timestamp selection with windows, equal timestamp tie-breaking with windows, consumption-trace accuracy, invalid verdict rejection inside a valid pass, payload mismatch rejection inside a valid pass, summary/report count agreement, and unchanged output headers.

Do not expose pass-window failures by changing the public report schema.
