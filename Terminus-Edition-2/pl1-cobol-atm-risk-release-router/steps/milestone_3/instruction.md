# Risk Thresholds And Supervisor Review Routing

Risk controls have been enabled using `/app/config/risk_thresholds.pli`, `/app/config/terminal_trust.psv`, and `/app/config/review_reason_precedence.psv`. A release that matches a hold and fits the card ledger is no longer always safe to commit automatically.

Apply the documented risk gates before updating exposure. Watchlisted cards, blocked or untrusted terminals, daily count or amount breaches, high-value terminal-threshold breaches, and insufficient exposure must be routed to `/app/out/manual_review_queue.psv` with one stable reason code. Also write `/app/out/risk_release_decisions.psv` for every processed release. Review-routed releases must not reduce card exposure until an approved manual commit is processed later.

Preserve the existing report header. Use `REVIEW` status for otherwise matched releases that require manual supervisor action, and keep unmatched releases distinct from review-routed releases.
