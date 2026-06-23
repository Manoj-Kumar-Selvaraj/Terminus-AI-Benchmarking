# photography reconciler client limit notes

Later milestones use `/app/config/client_limits.csv` with `client_id,package,max_refund_cents,enabled`. The limit is evaluated after package aliases and methods policy, and the last row for a client/package pair is authoritative.
