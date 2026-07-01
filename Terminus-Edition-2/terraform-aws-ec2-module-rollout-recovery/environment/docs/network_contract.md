# Placement and network contract

- Only subnets with `tier: private_app`, the configured account ID, unique IDs, and unique availability zones are eligible.
- At least `placement.minimum_azs` eligible zones must be present.
- Logical instance slots are stable JSON integers beginning at zero. Placement is derived from the sorted availability-zone identity, not input list order. `0` is correct; `"0"` and `"slot-01"` are not. The separate `tags.Slot` field is the decimal string form of that same integer.
- Capacity is balanced so the difference between the most- and least-populated zones is at most one.
- Existing slots keep their subnet assignment when subnet input order changes. Adding a new zone must not move existing slots unless capacity is explicitly changed.
- Instances never receive a public IP.
- `service_port` must be an integer from 1 through 65535. Zero, negative, above-range, blank, or non-integer values fail closed with an error containing `service_port`.
- Security-group ingress is exactly one object: `{"protocol":"tcp","from_port":service_port,"to_port":service_port,"source_security_group_id":network.alb_security_group_id}`.
- Security-group egress is exactly three scoped rules: one HTTPS endpoint rule `{"protocol":"tcp","from_port":443,"to_port":443,"prefix_list_ids": sorted endpoint_prefix_lists}`, then UDP and TCP resolver rules on port 53. Resolver rules must target `network.resolver_security_group_id`; either `source_security_group_id` or `destination_security_group_id` is accepted as long as the rule is scoped to that resolver security group.
- `alb_security_group_id` and `resolver_security_group_id` must start with `sg-`. `endpoint_prefix_lists` is required, every entry must start with `pl-`, and duplicate prefix-list IDs fail closed with an error containing `duplicates`.

## Validation error fragments

`validate` must fail closed with `error` text containing these substrings:

| Violation | Required substring in `error` |
|-----------|-------------------------------|
| Duplicate subnet ID | `duplicate subnet` |
| Duplicate availability zone | `duplicate availability` |
| Subnet tier not `private_app` | `private_app` |
| Subnet account not `account_id` | `configured account` |
| Fewer than `placement.minimum_azs` unique zones | `at least 3` (or the configured minimum) |
| Malformed ALB or resolver security group ID | `alb_security_group_id` or `resolver_security_group_id` |
| Missing endpoint prefix lists | `endpoint_prefix_lists is required` |
| Duplicate prefix list IDs | `duplicates` |
| Prefix list not starting with `pl-` | `start with pl-` |
| Invalid `service_port` | `service_port` |
