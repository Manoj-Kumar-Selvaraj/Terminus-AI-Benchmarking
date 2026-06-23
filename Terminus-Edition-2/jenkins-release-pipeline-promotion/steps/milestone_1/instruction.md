# Milestone 1 — Bind production deployment credentials without breaking staging

The release pipeline reaches the production promotion stage but authenticates with the staging credential. Use `/app/evidence/prod_auth_failure.log` and `/app/docs/release_promotion_contract.md` to repair `/app/ci/pipeline_config.json` while preserving the current Jenkins stage names and manifest schema.
