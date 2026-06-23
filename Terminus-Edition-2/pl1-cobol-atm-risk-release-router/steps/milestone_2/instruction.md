# Card Exposure Ledger

After strict eligibility is repaired, Risk Ops still sees card exposure totals drifting from the authorization ledger. The router now has to maintain the persistent card exposure view in `/app/data/card_exposure.psv` and write `/app/out/card_exposure_after.psv` after the batch.

Only a release that is otherwise eligible may reduce active exposure and increase the card's same-day released amount and count. A release for a missing card ledger row, or one whose amount exceeds the card's active hold exposure, must not be applied to the ledger. Preserve the existing release report and summary behavior from the base release decision.

The ledger is keyed by card and business date. Keep all untouched card rows, preserve risk flag text, and do not use the release report as a substitute for the exposure ledger.
