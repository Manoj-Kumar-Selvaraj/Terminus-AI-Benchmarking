# Report Contract

The CSV report is consumed by a downstream posting audit job. Keep the header and column order stable:

```text
invoice_id,customer_id,channel,amount_cents,payment_date,status
```
