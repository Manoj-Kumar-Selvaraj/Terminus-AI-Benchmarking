# Capacity pool and recovery contract

Regional capacity pools in `/app/data/capacity_pools.csv` represent the amount that can be credited for a canonical SKU type. Control totals in `/app/config/control_totals.csv` must reconcile committed group totals by region, SKU type, and billing cycle. The final milestone must commit groups in deterministic order and support restart after `ABEND_AFTER_GROUPS` without duplicating prior commits or skipping uncommitted groups.
