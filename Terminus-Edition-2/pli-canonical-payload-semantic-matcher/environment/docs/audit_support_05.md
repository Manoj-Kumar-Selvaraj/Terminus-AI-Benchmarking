# Producer alias drift

Feed `tm` renamed abbreviated segment codes (`f`, `a`, `s`) without updating canonical `segment_id` values in the expected catalog. Regression must honor `ALIAS_*` maps when alias mode is enabled.
