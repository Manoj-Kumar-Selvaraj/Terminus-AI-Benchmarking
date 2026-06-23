# Appointment feed layout

`appointments.csv` is header-addressed. Required columns for the current reconciler generation:

| Column | Meaning |
|--------|---------|
| `appointment_id` | Opaque booking identifier from the reservation system |
| `client_id` | Spa membership or guest account id |
| `amount_cents` | Service price in integer cents |
| `status` | Booking lifecycle state; only completed visits are refundable |
| `service_area` | Treatment category (massage, facial, sauna, etc.) |

Later export formats may add optional columns such as `service_date`. Extra columns must be
ignored when absent from a given file version. Identifiers and amounts may include surrounding
whitespace in raw exports; finance expects normalization before matching.

Appointment rows are consumed at most once per batch. Duplicate `appointment_id` values in
separate physical rows represent separate consumable inventory, not a single shared slot.
