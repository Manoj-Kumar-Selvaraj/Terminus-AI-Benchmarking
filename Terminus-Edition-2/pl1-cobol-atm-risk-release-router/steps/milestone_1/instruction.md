# Strict Release Eligibility

Operations has traced several suspicious automatic ATM hold releases to the router under `/app`. The batch is still launched through `/app/scripts/run_batch.sh`, reads the pipe-delimited inputs under `/app/data`, and must preserve the existing `release_report.csv` and `release_summary.txt` contracts documented under `/app/docs`.

Restore the base release decision so a release can clear only against one eligible source hold with the same hold id, card id, terminal id, region, channel, and amount. The eligible hold status and allowed release reasons come from `/app/src/release_rules.pli`; the shell harness, report schema, and pipe-delimited source files are fixed interfaces.

Each source hold can be consumed once. Invalid statuses, invalid reasons, malformed or mismatched keys, wrong channels, and duplicate release attempts must remain unmatched without changing the existing report header or summary keys.
