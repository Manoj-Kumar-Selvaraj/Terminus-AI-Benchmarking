# Schema Compare Windows

Regression checks run only during approved compare windows per `schema_id`. Each window row in `/app/config/compare_windows.psv` carries:

- `open_ts` / `close_ts` — inclusive 14-digit UTC bounds
- `state` — must equal `OPEN_COMPARE_STATE` from the rules deck for the window to admit traffic

Both the expected catalog `recv_ts` and the actual check `check_ts` must fall inside the same open window for the row's `schema_id`.
