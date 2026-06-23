GET /rail/{rail} returns JSON with rail and allowed fields.

The local verifier may run the Java adapter without the Compose `rules` service.
When the service is unreachable, the adapter should read allowed rails from
`/app/config/rails.csv` at runtime rather than failing the batch. The shipped
file allows ACH, WIR, and RTP; verifier tests may rewrite that file.
