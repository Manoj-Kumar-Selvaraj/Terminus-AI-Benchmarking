# Matching rules

Credits match tickets on full `ticket_id`, `traveler_id`, `amount_cents`, `FLOWN` status, and exact `fare_class` equality after normalization. Each ticket row is consumed at most once. Report rows follow credit input order; summary amounts are positive integer cents.
