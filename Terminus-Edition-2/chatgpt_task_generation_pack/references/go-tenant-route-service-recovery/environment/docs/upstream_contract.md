# Upstream contract

The router is not the owner of upstream business errors. It should preserve
successful upstream status codes, treat unreachable upstreams as gateway errors,
and enforce the route SLO when an upstream stalls.

The router should not accumulate idle resources when upstream calls fail.
