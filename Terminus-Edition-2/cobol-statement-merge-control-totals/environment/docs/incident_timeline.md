# Incident timeline

23:40 UTC: nightly statement merge started for cycle 20260401. Manifest listed two sort runs.

23:52 UTC: operations noted `/app/out/merge_summary.txt` `total_debit_cents` diverged from
sort-run hash totals. First sort run contained a non-monotonic composite key sequence for
account `ACCT1001`.

00:04 UTC: after adding run02, duplicate composite keys at the run boundary produced split
accumulator state. Control totals for `ACCT1001/20260401` were lower than expected.

00:11 UTC: file-transition commit assigned the closing group for `ACCT1001/20260402` to the
next account opened from run02.

00:18 UTC: ABEND during checkpoint window. Rerun doubled committed debits for the first two
groups before operators halted the job.

00:31 UTC: batch disabled pending COBOL merge repair.
