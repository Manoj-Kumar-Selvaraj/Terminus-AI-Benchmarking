# Output contract

The module must preserve downstream output names including `vnet_id`, `subnet_ids`, private endpoint identifiers, route table maps, and DNS zone references.

Output expressions must reference created module resources rather than hardcoded address maps from the failed cutover state.
