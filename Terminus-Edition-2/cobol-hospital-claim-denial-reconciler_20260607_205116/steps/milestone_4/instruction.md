Hospital compliance controls now accompany the denial feed. Update `/app/src/claim_denial_reconcile.cbl` and keep `/app/scripts/run_batch.sh` as the executable entrypoint.

The original fixed-width records now carry the suffix documented in `/app/docs/record_layouts.md`. A denial can clear only when `hospital_code` and `state_code` match exactly after padding normalization, and the selected source claim has `supporting_documents_validated` equal to `Y` case-insensitively. Blank, malformed, or unapproved compliance fields are ineligible. All established identity, amount, branch, status, reason, service alias, date, calendar, candidate-ranking, and one-time-consumption rules still apply.

Legacy mainframe feeds may pad textual fields with binary low-values (`X'00'`) instead of spaces. Treat low-values as spaces in textual source, denial, calendar, and OFAC fields before trimming or comparing them. Do not allow low-values in amount or date fields, and never emit a low-value into either output file.

Apply OFAC decisions from `/app/config/ofac_screening.dat`. For the denial account and hospital, consider only rows with a numeric `screen_date` on or before the action date. Select the latest eligible screen date, breaking ties by earliest OFAC input row. The selected decision must be exactly `CLEAR` after trimming and case folding. `HOLD`, `BLOCK`, unknown decisions, future decisions, malformed dates, or a missing applicable row must fail closed. OFAC rejection must not consume a source claim.

Continue to write `/app/out/denial_report.csv`, `/app/out/denial_summary.txt`, and `/app/out/source_consumption.csv` with the established schemas, action order, exact status labels, blank unmatched service fields, preserved reasons, matched-row source trace, and positive cent totals.
