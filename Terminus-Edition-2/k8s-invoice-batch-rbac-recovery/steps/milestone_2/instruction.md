After authorization was restored, finance reported duplicate ledger artifacts for the same billing window when the nightly batch overran its schedule slot. Review `/app/evidence/duplicate_ledger.log` and `/app/docs/publication_contract.md`.

Ensure only one artifact is published per billing window even when a prior run is still active. The overlap fixture in `/app/sim/config.json` uses billing window `WIN-20260612`, and the publication contract names its single ledger artifact `ledger-WIN-20260612`. Keep the milestone 1 configuration-read recovery intact.
