# Restart recovery

`/app/out/payment_ledger.psv` is the committed side-effect journal. If a rerun sees a
previously committed event id, it must skip that payment side effect without treating the
claim as newly payable. `/app/out/restart_checkpoint.txt` records the last committed
instruction and total committed rows observed by the process using:

```text
last_committed_instruction_id=PAY-<claim_id>-<event_id>
last_committed_event_id=<event_id>
committed_count=<integer>
```

When `ABEND_AFTER_COMMITS` stops the batch, the process must exit non-zero after writing
this checkpoint.
