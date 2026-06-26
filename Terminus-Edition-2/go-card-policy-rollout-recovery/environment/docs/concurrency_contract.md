# Worker, lease, and generation contract

Multiple controller processes and multiple workers may share one state directory. Claims and journal appends must therefore be process-safe. A live delivery may have only one unexpired claim, and competing workers must not both issue a request for that claim.

A claim lasts 30 logical seconds from the `--now-unix` value. A worker that stops after claiming leaves the delivery in `claimed` state. Another worker at or before `lease_until` must leave it untouched. A worker after `lease_until` may take it over, must increment the claim token, and must reuse the stable command identity. Completion from an older claim token must not overwrite the newer owner's result.

Newer generations are eligible while an older generation is in flight. If a delayed older request returns after a newer generation is active, regional state must not regress. The gateway rejects the old generation, and the controller records the older delivery as `superseded` while keeping the newer delivery `acked`. A locally pending rollout already below the controller's durable regional active generation is superseded without sending another gateway request.
