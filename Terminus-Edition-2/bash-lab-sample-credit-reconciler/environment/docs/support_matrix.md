# Supported payer and status matrix

| Sample status | Allowed payers | Notes |
|---------------|----------------|-------|
| FINAL | CASH, CARD, INSURANCE | Primary supported set |
| FINAL | CC, INS, CA | Legacy aliases normalize to CARD, INSURANCE, CASH |
| Other | Any | Not eligible for matching |

Dated batches additionally require both `credit_date` and `result_date` to be open calendar days within the configured two-open-day window.
