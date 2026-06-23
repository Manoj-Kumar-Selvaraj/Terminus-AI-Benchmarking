# Charity pledge adjustment reconciler

This service matches pledge adjustments from `/app/data/adjustments.csv` against booked pledges in `/app/data/pledges.csv`. The batch entrypoint is `/app/lib/reconcile.rb`, which delegates to `Charity::Runner`.

## Layout

| Path | Role |
|------|------|
| `lib/charity/csv_loader.rb` | Parses pledge and adjustment CSV rows |
| `lib/charity/fund_registry.rb` | Loads enabled funds and legacy aliases from config |
| `lib/charity/matcher.rb` | Pledge-to-adjustment matching rules |
| `lib/charity/calendar.rb` | Reads open dates from `config/cutoff_calendar.txt` |
| `lib/charity/report_writer.rb` | Writes report CSV and summary JSON |
| `config/methods.csv` | Canonical fund codes and enable flags |
| `config/donor_limits.csv` | Donor-and-fund adjustment caps and enable flags |
| `config/fund_aliases.json` | Legacy export alias map |

See `matching_rules.md`, `fund_aliases.md`, and `date_gating.md`, and `donor_limits.md` for business rules.
