# Card policy rollout controller

The controller distributes emergency card-fraud policy revisions to regional authorisation gateways. Operators enqueue a rollout once, then one or more workers deliver the same policy revision to every configured region. Controller state is local and durable so an interrupted worker can be restarted without deleting the state directory.

The regional gateways are independent persistent services. They accept policy application requests over HTTP, remember every delivery identity, reject older generations after a newer one is active, and expose their durable state through `/debug/state`. The controller and gateways are deliberately separate processes because remote application can succeed even when the controller dies before recording the acknowledgement.

The supported binaries are `/app/bin/rolloutctl` and `/app/bin/gatewayd`. Build them from the Go sources with `/app/scripts/build.sh`. The public CLI and state contracts in this directory are compatibility requirements; repair the implementation rather than replacing the binaries with scripts or editing evidence and tests.
