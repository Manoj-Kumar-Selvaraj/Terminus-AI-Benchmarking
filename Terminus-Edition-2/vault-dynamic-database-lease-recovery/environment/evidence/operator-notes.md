# Operator notes

Do not delete `/app/state` during recovery: it is the only application-side record that ties pod ownership, request identity, pool generations, and uncertain issuance outcomes together. The static credential reference was an emergency workaround and is not approved for application use. Keep both response protocols working during the rollout. The runtime clock is authoritative for all incident reproduction; wall-clock sleeps made the original staging test misleading.
