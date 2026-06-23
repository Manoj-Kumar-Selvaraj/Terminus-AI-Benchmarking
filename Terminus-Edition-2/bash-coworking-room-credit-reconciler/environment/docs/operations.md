# Coworking room credit reconciler

The batch reads booking and credit CSV exports from `/app/data`, applies membership and room-plan eligibility rules, and writes a report plus summary under `/app/out`.

CSV exports are simple comma-delimited files without quoted commas. Operators may reorder columns or add ignored columns, so reconciliation code should address columns by header name rather than fixed position.
