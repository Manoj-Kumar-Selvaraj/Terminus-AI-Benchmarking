# Theater booking refund reconciler

Matches patron refunds in `/app/data/refunds.csv` to ticketed bookings in `/app/data/bookings.csv`. Entry point: `/app/lib/reconcile.rb` → `Theater::Runner`.

| Module | Role |
|--------|------|
| `lib/theater/csv_loader.rb` | Parse booking and refund CSV rows |
| `lib/theater/seat_zone_registry.rb` | Enabled zones and legacy aliases |
| `lib/theater/matcher.rb` | Core matching rules |
| `lib/theater/calendar.rb` | Open dates from `config/cutoff_calendar.txt` |
| `lib/theater/report_writer.rb` | Write report CSV and summary JSON |

See `matching_rules.md`, `seat_aliases.md`, and `date_gating.md`.
