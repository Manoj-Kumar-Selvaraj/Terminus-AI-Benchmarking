The general ledger PL/I posting normalizer rejects valid journal matches. Fix `/app/src/posting_batch.pli`, `/app/src/posting_rules.pli`, or the batch harness.

Milestone 2 keeps milestone 1 rules and enables `ALIAS_*` ledger-class normalization. Emit canonical `ledger_class` for posted rows.
