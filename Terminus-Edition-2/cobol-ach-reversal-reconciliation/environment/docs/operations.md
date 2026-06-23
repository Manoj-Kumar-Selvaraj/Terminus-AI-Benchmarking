# ACH Reversal Operations Notes

Same-day reversal processing compares reversal rows against posted settlement
rows. Operators review `/app/out/reversal_report.csv` for any `UNMATCHED`
entries before releasing the summary to downstream settlement accounting.
