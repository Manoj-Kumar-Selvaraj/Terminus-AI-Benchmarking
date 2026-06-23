# Operations Notes

Escrow disbursements are cleared by closing package, not by independent row success. A row may match a hold while its package remains held because a required kind is missing, the expected package total is wrong, trust funding is insufficient, or the operator control totals do not reconcile.

Closing-package commit boundaries are the only restart-safe checkpoint boundaries.
