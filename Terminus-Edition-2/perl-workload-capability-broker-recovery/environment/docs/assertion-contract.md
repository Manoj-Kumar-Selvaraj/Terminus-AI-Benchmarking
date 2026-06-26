# Signed workload assertion contract

The broker accepts compact `SWA1` assertions signed with HMAC-SHA256. The protected header contains `alg`, `typ`, and `kid`; the payload contains `iss`, `sub`, `tenant`, `aud`, `scope`, `jti`, `iat`, `nbf`, `exp`, `source_epoch`, and optional `act` delegation principals. Verification is bound to the claim issuer: key identifiers are not globally unique. Only `active` and `retiring` issuer keys verify. Audience comparison is exact against one array member, and the tenant must belong to the issuer. The configured clock skew applies symmetrically to `nbf`, `iat`, and `exp`.

The original compact bytes are the signed input. Verification must not rewrite or reserialize claims before checking the signature. Assertion verification is read-only and must not replace issuer, broker signer, subscription, or journal identities.
