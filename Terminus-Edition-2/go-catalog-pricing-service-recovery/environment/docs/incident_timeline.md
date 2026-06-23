# Incident timeline — catalog pricing service

- 20:05 UTC: the read-through cache release reached all pricing-service instances.
- 20:17 UTC: catalog version 42 was published for `CAMERA-4K`; an invalidation event carrying `minimum_version: 42` was acknowledged by the service.
- 20:17:01 UTC: a request that began before the event completed afterward and the instance continued serving version 41 until its TTL elapsed.
- 20:42 UTC: the regular expiry boundary caused catalog traffic to jump from 80 requests/second to more than 2,000 requests/second while client traffic was steady.
- 21:06 UTC: mobile clients using the version 1 response contract began rejecting successful responses after the cache metadata rollout.

The fixes belong to the existing service. Do not replace the pricing source with hard-coded product data, disable caching, or remove invalidation handling.
