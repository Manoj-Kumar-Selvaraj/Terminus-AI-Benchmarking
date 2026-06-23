# Restart recovery contract

The batch can be interrupted deterministically by setting `ABEND_AFTER_COMMITS`. A committed release is recorded in `/app/out/risk_release_journal.psv` while its card exposure and terminal cash mutations are persisted before the checkpoint advances. On rerun, the router must read the committed journal, skip already committed release ids, continue pending releases, and avoid duplicating journal rows, exposure updates, cash dispense updates, or manual-review postings.
