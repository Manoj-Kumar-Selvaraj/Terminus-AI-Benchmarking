# Service catalog

The spa groups treatments into three billable service areas used in exports and refund
tickets:

| Service area | Typical offerings |
|--------------|-------------------|
| `MASSAGE` | Swedish, deep tissue, hot stone |
| `FACIAL` | Classic, hydrating, anti-aging |
| `SAUNA` | Infrared suite, steam room packages |

Front-desk shorthand and vendor-specific labels sometimes appear in raw CSV rows. Canonical
names above are what finance publishes in cross-system reports. Reconciliation should not
treat prefix fragments of ids or service tokens as equivalent to full values.

Unsupported or experimental treatment codes may appear in pilot exports; those rows should
not clear unless they resolve to a recognized catalog entry through the deployment's mapping
rules.
