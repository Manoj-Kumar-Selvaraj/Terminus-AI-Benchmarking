# Cache consistency contract

The cache key is the normalized `(SKU, currency)` pair. An invalidation event applies to every currency for its SKU and carries the minimum catalog version that may be cached after the event is acknowledged.

A request already fetching when an invalidation is acknowledged may complete with the older value. It must not repopulate the cache with a version below the event's minimum. Events can be duplicated or arrive out of order, so an older event must not lower an already-recorded minimum version.

TTL expiry remains enabled. Prices are read from the configured `catalog.Source`; product values and catalog versions must not be hard-coded into the service.
