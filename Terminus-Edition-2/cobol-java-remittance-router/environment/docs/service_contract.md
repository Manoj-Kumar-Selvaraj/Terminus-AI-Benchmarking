GET /rail/{rail} returns JSON with rail and allowed fields.

The local verifier may run the Java adapter without the Compose `rules` service.
When the service is unreachable, the adapter should fall back to the same rail
allow-list mirrored in `/app/config/rails.csv` rather than failing the batch.
