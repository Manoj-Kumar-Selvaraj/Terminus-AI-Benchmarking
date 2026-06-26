# Release identity contract

The approved `release_artifact` is authoritative. The mutable AMI catalog alias is evidence only and must never select production identity. `launch_template.ami_id`, `architecture`, `user_data_sha256`, and provenance fields must come from `release_artifact`, not `ami_catalog.latest`. `launch_template.provenance` is exactly the three-key object `{commit_sha, build_id, manifest_sha256}` copied from `release_artifact`; do not include the full release artifact or any extra provenance keys in that launch-template field.

The manifest digest is lowercase SHA-256 over canonical JSON containing exactly these keys, sorted lexicographically with compact separators:

- `manifest_version`
- `ami_id`
- `ami_owner_account_id`
- `architecture`
- `commit_sha`
- `build_id`
- `user_data_sha256`

`manifest_sha256` is not included in its own digest input.

Validation fails closed when a field is absent, the digest is inconsistent, the AMI is absent from the catalog, the owner or architecture differs, the image is not `available`, or it is deprecated.

A launch-template version is a deterministic digest of immutable release identity, instance type, metadata options, and bootstrap hash. Reordering JSON keys must not change it. Reapplying the same approved release must not synthesize another version.

Launch-template and instance tags carry release provenance. Required tag keys are `Application`, `Environment`, `CommitSha`, `BuildId`, and `ReleaseManifestSha256`; instance tags also include `Slot` as the logical slot string. The `ReleaseManifestSha256` tag value is exactly `release_artifact.manifest_sha256`.

Fail-closed validation errors must name the field family that failed so operators can repair the manifest: missing manifest fields use `release_artifact.<field> is required` such as `release_artifact.manifest_version is required`, unknown AMIs name `ami_catalog.images`, catalog owner mismatches contain `owner`, unavailable images contain `available`, and deprecated images contain `deprecated`.
