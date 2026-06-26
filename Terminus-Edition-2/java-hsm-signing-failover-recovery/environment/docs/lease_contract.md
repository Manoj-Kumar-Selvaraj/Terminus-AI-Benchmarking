# Signing Lease and Fencing Contract

The card-network signing gateway has two warm nodes but only one node may issue HSM operations. The coordinator provides the integer `--now` value used by every command; host wall clocks are not authoritative.

A lease token is `<node>:<epoch>`. Acquisition rules:

- if no lease is active, acquisition increments the durable epoch, records the owner, and sets `expires = now + lease_ms`;
- an active owner reacquiring its own lease receives the same token and does not extend it;
- another node cannot acquire until `now >= expires`;
- takeover increments the epoch even when the same node name later returns;
- renewal requires the exact current token and an unexpired lease, keeps the epoch, and sets a new expiry;
- every privileged command validates owner, epoch, and expiry while holding the state lock.

The lease state must be updated atomically. Concurrent acquisition attempts at the same coordinator time may yield only one active owner.
