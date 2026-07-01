# Incident timeline

A private endpoint and egress cutover regression left the secure VNet module with legacy singleton subnets, Internet default routes, and moved-block drift relative to imported state.

Reviewers halted the change after plan review showed mixed egress semantics and endpoint placement outside the dedicated private endpoint subnet.
