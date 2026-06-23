Continue the remittance router work in `/app`. The Java payload still mishandles duplicate transaction ids after the COBOL export is correct.

Keep milestone 1 behavior and outputs: `/app/out/remit_export.csv`, `/app/out/remit_summary.txt` (`exported_count`, `exported_amount_cents`, `rejected_count`), and `/app/out/remit_payload.json` per `/app/config/payload_schema.json` and `/app/docs/payload_contract.md`.

**Rules service** - Try the URL from `RULES_URL` when available; if the service cannot be reached during verification, read allowed rails from `/app/config/rails.csv` at runtime (do not hardcode a fixed rail list in Java). The shipped file allows `ACH`, `WIR`, and `RTP`, but tests may modify `rails.csv`. The adapter must not crash when the rules service is unavailable.

**Duplicate transaction ids** - If the export contains the same `transaction_id` more than once, only the earliest exported row can be `ACCEPTED`; later rows with that id must stay in the payload in export order with status `DUPLICATE`, must not count toward `accepted_count` / `accepted_amount_cents`, and must count in `rejected_count`. Preserve 10-character zero-padded `amount_cents` strings on every transaction object.
