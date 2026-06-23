# Privilege Mandate Sandbox Classifier

Service security reviews compare live sandbox audits in `/app/data/sandbox_audits.psv` against signed mandates in `/app/data/mandates.psv`. Policy constants are DCL declarations in `/app/src/mandate_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/mandate_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Mandate registry** (`/app/data/mandates.psv`): `mandate_id`, `service_id`, `cap_token`, `payload_hash`, `sandbox_class`, `recv_ts`, `state`, `kind_code`.

**Sandbox audits** (`/app/data/sandbox_audits.psv`): `claim_id`, `mandate_id`, `service_id`, `cap_token`, `payload_hash`, `audit_ts`, `verdict_code`, `sandbox_class`.

**Sandbox windows** (`/app/config/sandbox_windows.psv`, milestone 3): `service_id`, `open_ts`, `close_ts`, `state`.

See `/app/docs/mandate_matching.md` for authorization rules.

## Outputs

`/app/out/mandate_report.csv`:

`claim_id|mandate_id|service_id|audit_class|sandbox_class|cap_token|verdict_code|status`

`/app/out/mandate_summary.txt`:

`authorized_count`, `authorized_mandates`, `denied_count`, `denied_mandates`
