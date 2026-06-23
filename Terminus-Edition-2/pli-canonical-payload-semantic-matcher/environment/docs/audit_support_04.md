# Incident 2026-06-12 — false DIFFER on schema 991100

Checks with identical five-key tuples were marked `DIFFER` when two expected rows shared a prefix-only match. Operators suspect `KEY_COMPARE` and consumption settings in the batch deck.
