# Route refresh protocol

Route snapshots are whole-service observations from the control plane. A newer
snapshot replaces the previous active set. Tenants absent from the new snapshot
should no longer be routable after the refresh is applied.

Refresh may overlap with requests. Request handlers should observe a consistent
snapshot for each lookup.
