# CIDR and imported-state migration

Preserve Milestones 1 and 2. Extend recovery to validate subnet CIDRs and reconcile imported Terraform state without replacing existing imported identities.

Requirements:

- Reject subnets outside `vpc_cidr` before mutation with error substring `outside vpc_cidr`.
- Reject exact, containing, contained, or partial subnet overlaps before mutation with error substring `overlaps`.
- Reject ambiguous imported-state matches for the same CIDR before mutation with error substring `ambiguous imported cidr`.
- Match imported legacy subnet resources by CIDR, including legacy addresses such as `module.vpc.aws_subnet.private[0]`.
- Preserve imported subnet IDs and imported route table IDs when a configured subnet CIDR matches imported state.
- Recovered app subnet objects must keep their evidence-derived `address`, `id`, `cidr`, `tier`, `az`, and `route_table_id` fields.
- Emit deterministic moved entries in recovered state under the top-level `moved` array, not only in `plan_actions`. Each moved entry must be shaped as `{"action": "moved", "from": "<legacy address>", "to": "<current subnet address>"}`.
- The legacy imported app subnet moves must map `module.vpc.aws_subnet.private[0]`, `[1]`, and `[2]` to the current app subnet address for the same CIDR.
- Adding a new AZ must create only new subnet and route-table identities for the new CIDRs, while preserving unchanged imported subnet IDs and route table IDs.
- AZ expansion must not emit destructive `replace` actions in `plan_actions` for unchanged imported resources.
- `outputs.private_app_route_table_ids` must remain present and must use imported app route table IDs when imported state provides them.
- Gateway endpoint associations must follow `outputs.private_app_route_table_ids`, so endpoint route tables use imported app route table IDs rather than generated names.
- Milestone 1 routing and Milestone 2 gateway endpoint behavior must remain intact after imported-state recovery.