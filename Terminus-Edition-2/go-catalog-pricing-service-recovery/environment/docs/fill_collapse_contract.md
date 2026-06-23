# Read-through fill contract

When a `(SKU, currency)` entry is absent or expired, concurrent callers for that same key share one active source fetch. Once the fetch completes, all waiting callers receive the same outcome and the successful value is cached.

Different keys must remain independent: a slow fetch for one SKU or currency cannot block a source fetch for another key. Cache hits must not call the source, and invalidation/version guarantees continue to apply to a shared in-flight fill.
