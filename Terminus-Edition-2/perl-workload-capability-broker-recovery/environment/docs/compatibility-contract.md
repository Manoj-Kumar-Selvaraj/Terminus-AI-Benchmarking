# Compatibility and protected boundaries

Preserve `/app/bin/brokerctl`, compact `SWA1` and `CAP1` token shapes, issuer names, tenant names, key IDs, policy generation field, capability serials, state JSON schemas, and append-only journals. The Go runtime under `/opt/task-tools` and its baseline fixtures are trusted and must not be changed. Do not solve the incident by accepting unsigned assertions, disabling expiry, removing delegation, clearing replay state, assigning huge serials, replacing key identities, fabricating rotation completion, or returning canned tokens.
