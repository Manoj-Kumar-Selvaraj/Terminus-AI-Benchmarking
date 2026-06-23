# Versioned HTTP response contract

Routes remain `GET /v1/prices/{sku}` and `GET /v2/prices/{sku}`. Currency is selected with the optional `currency` query parameter and defaults to `USD`.

## Version 1 success

The JSON object contains exactly `sku`, `currency`, `amount_minor`, and `promotion`. The `promotion` member is always present and is `null` when no promotion applies. Version 1 must not expose catalog version or cache metadata.

## Version 2 success

The JSON object contains `sku`, `currency`, `amount_minor`, and `catalog_version`. `promotion` is present only when a promotion applies. Cache status and other internal metadata are not part of either public schema.

## Missing price

Both versions return HTTP 404 with exactly `{"code":"price_not_found","sku":"<NORMALIZED-SKU>"}`. Successful and not-found responses use `application/json`. Preserve the existing routes, query parameter, service interface, and numeric minor-unit representation.
