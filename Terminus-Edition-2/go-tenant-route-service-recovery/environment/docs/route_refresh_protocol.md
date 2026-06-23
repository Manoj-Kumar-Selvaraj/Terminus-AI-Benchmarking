# Route refresh protocol

Route snapshots are whole-service observations from the control plane. A newer
snapshot replaces the previous active set. Tenants absent from the new snapshot
should no longer be routable after the refresh is applied.

Refresh may overlap with requests. Request handlers should observe a consistent
snapshot for each lookup.

Each route stored during `Refresh` must use the snapshot revision as its
`Revision` value so response headers reflect the active snapshot.

Refresh revisions are monotonic. Once a snapshot has been accepted, a later
call to `Refresh` with the same or an older revision is a replay and must leave
the active route set unchanged.
