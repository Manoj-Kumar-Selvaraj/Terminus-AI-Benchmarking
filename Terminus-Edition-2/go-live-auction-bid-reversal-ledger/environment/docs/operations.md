# Operations

The realtime reversal ledger runs during live auctions. Duplicate reversal events are common after retry storms, so source bid rows must be consumed at most once. Runtime configuration may be overwritten by the verifier before the batch runs.
