# Recover immutable launch-template provenance

The payments API rollout selected an unapproved machine image even though the release manifest in `/app/evidence/release_manifest.json` was approved. Operators also observed that equivalent reruns produced different launch-template identities.

Work offline. Use `/app/tools/ec2sim`, `/app/docs/release_contract.md`, `/app/docs/module_contract.md`, and the incident evidence. Repair the existing Go EC2 module rather than replacing the simulator or fabricating output.

## Required behavior

- `plan` and `apply` use the complete approved `release_artifact` identity, never the mutable catalog alias (`ami_catalog.latest`).
- `launch_template.provenance` must be exactly the three release fields `commit_sha`, `build_id`, and `manifest_sha256`; do not embed the full release artifact or any extra keys there.
- Validate the normative canonical manifest digest and catalog provenance, including owner account, architecture, availability, and deprecation state.
- Missing or inconsistent release fields fail closed with field-specific errors such as `release_artifact.manifest_version is required`.
- Equivalent JSON ordering produces the same launch-template version and state digest.
- Replanning the same approved release preserves launch-template and logical instance identity.
- Instance tags retain exact slot, commit, build, and release-manifest provenance.
- `apply` atomically writes the complete state and appends one JSONL journal record. Each record includes `operation_id`, `release_manifest_sha256` from the approved artifact, `refresh_status`, and the rendered `state_digest`; with no `--journal`, use `${state}.journal.jsonl`.
- Preserve the documented CLI, Terraform resource labels, and output keys.

Do not hardcode the production sample, edit verifier files, modify the simulator CLI, or call AWS or Terraform.
