# Pin launch template identity to the release artifact

You are recovering a Terraform AWS EC2 module rollout for the payments API fleet. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/ec2sim.py`, `/app/docs/module_contract.md`, and `/app/evidence`.

Use immutable AMI, commit, build, and user-data hash from the release artifact and fail closed when fields are missing.

## Success criteria

- `plan` and `apply` pin `launch_template.ami_id`, `user_data_sha256`, `provenance.commit_sha`, and `provenance.build_id` to `release_artifact` values (not `ami_catalog.latest`).
- `validate` rejects missing `ami_id`, `commit_sha`, `build_id`, or `user_data_sha256` with errors containing `release_artifact.<field>`.
- Instances carry `CommitSha` and `BuildId` tags from the artifact; `outputs.launch_template_version` matches the template version.
- `ec2sim.py` accepts `--prior-state` and `--state` on `plan`/`apply` without error.

Compatibility constraints: keep `/app/infra/modules/ec2`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
