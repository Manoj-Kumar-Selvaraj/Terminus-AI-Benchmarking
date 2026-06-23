# Incident timeline

02:14 UTC: route refresh job started during a routine tenant migration.

02:15 UTC: several edge pods terminated while serving traffic. The last log
line from one pod references a runtime fatal error during a route lookup.

02:19 UTC: after a hot patch reduced immediate exits, the same route path began
showing increasing goroutine and file descriptor counts during upstream 5xx
bursts.

02:28 UTC: a deploy restart dropped a small number of accepted requests.

02:34 UTC: a single stalled upstream held client connections longer than the
published service contract allows.
