# Reservation cycle settlement contract

The reconciler is no longer only a row matcher. After individual credits are evaluated, matched credits must roll up into reservation-cycle groups from `/app/config/reservation_cycles.csv`. A group clears only when all required SKU categories are represented by matched credits, the matched amount equals the expected amount, and no member credit is unmatched. Held groups must not consume regional capacity.

The group output is `/app/out/reservation_credit_groups.csv`.
