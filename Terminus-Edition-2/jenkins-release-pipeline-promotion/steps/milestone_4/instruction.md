# Milestone 4 — Rollback to prior production artifact without rebuilding HEAD

The rollback stage still rebuilds HEAD after a failed release. Use `/app/evidence/rollback_postmortem.md`. Rollback must redeploy the prior production artifact digest from deploy history and must not change the stage names or manifest schema.
