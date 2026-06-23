The multicurrency ledger clearing processor rejects postings when treasury submits abbreviated currency codes. Fix only the PL/I-style control files under `/app/src` so `/app/data/postings.psv` reconciles against `/app/data/ledger.psv`. Do not modify `/app/scripts/run_batch.sh` or `/app/scripts/pli_ledger.awk`; `/app/out/ledger_report.csv` remains pipe-delimited.

Preserve the existing full-key matching, consumption, posting-order, report, and summary rules. Enable `ALIAS_*` normalization from `/app/src/ledger_rules.pli` (`raw=>canonical`, case-insensitive on compare keys). Matching compares canonical values; emit canonical `currency_code` on `CLEARED` rows only, and leave it blank on `HELD` rows.

Read all constants and aliases dynamically from `/app/src/ledger_rules.pli`; the verifier may replace the rules and input files with different values. Ignore `/app/config/fx_windows.psv` for this run. Status must be exactly `CLEARED` or `HELD`.
