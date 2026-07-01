# Milestone 5 — make the module migration-safe

The rollout was stopped because Terraform planned destructive replacement of legacy network objects after the module refactor. Preserve all previous behavior while adding migration metadata so the retired legacy subnet, route table and route-table-association addresses are moved into the new stable keyed resources instead of recreated.

Keep resources keyed by logical names such as `app` and `data`, add `prevent_destroy` lifecycle guards to core network resources, and add a precondition that private endpoints cannot be planned unless `var.private_endpoint_subnet_key` points to a declared subnet. Validate administrator CIDRs so `0.0.0.0/0` and `::/0` are rejected, and keep the task plan-only by avoiding live Azure lookups, random resources, timestamps, backend/provider ownership, apply scripts and generated cloud-state artifacts.
