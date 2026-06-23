After readiness recovered, soak charge traffic began returning database errors and `pool exhausted` messages while invalid charge attempts repeated. Review `/app/evidence/pool_soak.log` and `/app/docs/pool_contract.md`. Restore charge handling so repeated validation failures do not exhaust the JDBC pool.

Preserve the milestone 1 datasource and readiness behavior. The verifier posts many invalid charges, confirms the pool returns to idle capacity, and still reads invoices successfully.
