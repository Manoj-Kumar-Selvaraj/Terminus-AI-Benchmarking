# Placement and network contract

- Only subnets with `tier: private_app`, the configured account ID, unique IDs, and unique availability zones are eligible.
- At least `placement.minimum_azs` eligible zones must be present.
- Logical instance slots are stable integers beginning at zero. Placement is derived from the sorted availability-zone identity, not input list order.
- Capacity is balanced so the difference between the most- and least-populated zones is at most one.
- Existing slots keep their subnet assignment when subnet input order changes. Adding a new zone must not move existing slots unless capacity is explicitly changed.
- Instances never receive a public IP.
- `service_port` must be an integer from 1 through 65535. Zero, negative, above-range, blank, or non-integer values fail closed with an error containing `service_port`.
- Security-group ingress is exactly one object: `{"protocol":"tcp","from_port":service_port,"to_port":service_port,"source_security_group_id":network.alb_security_group_id}`.
- Security-group egress is exactly three objects in this order: one HTTPS endpoint rule `{"protocol":"tcp","from_port":443,"to_port":443,"prefix_list_ids": sorted endpoint_prefix_lists}`, then UDP and TCP resolver rules on port 53 with `source_security_group_id` equal to `network.resolver_security_group_id`.
- `alb_security_group_id` and `resolver_security_group_id` must start with `sg-`. `endpoint_prefix_lists` is required, every entry must start with `pl-`, and duplicate prefix-list IDs fail closed with an error containing `duplicates`.
