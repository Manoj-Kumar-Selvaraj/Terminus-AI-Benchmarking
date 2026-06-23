# Card exposure contract

The ATM release router is no longer only a hold/release row matcher. Eligible releases must be applied against a persistent card exposure ledger. The ledger tracks active authorization hold exposure, same-day released amount, release count, and risk flags. Only committed automatic releases and approved manual releases reduce active exposure and increase released totals.

The report `/app/out/card_exposure_after.psv` must preserve all card rows and write one row per card/business date after processing. Manual-review and rejected releases must not reduce exposure until a later approved release commit.
