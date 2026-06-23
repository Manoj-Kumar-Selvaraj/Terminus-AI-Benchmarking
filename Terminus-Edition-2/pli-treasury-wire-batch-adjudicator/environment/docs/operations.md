# Treasury Wire Batch Adjudicator
Reconciles pipe-delimited `/app/data/claims.psv` against `/app/data/clearing.psv` using PL/I decks in `/app/src/`. Rail aliases are case-folded for comparison only; cleared rows emit the canonical spelling from each `ALIAS_*` declaration. Batch feature switches in `wire_batch.pli` gate window, cutoff, ledger, liquidity, and sanctions behavior.
