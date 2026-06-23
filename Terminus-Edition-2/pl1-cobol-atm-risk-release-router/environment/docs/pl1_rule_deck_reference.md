# PL/I Rule Deck Reference

`/app/src/release_rules.pli` declares:

- `ELIGIBLE_HOLD_STATUS` — only holds with this status may match.
- `REASON_APPROVE`, `REASON_REVIEW`, `REASON_EXPIRE` — allowed release reasons.
- `ALIAS_ATM`, `ALIAS_POS`, `ALIAS_WEB` — `raw=>canonical` channel aliases (milestone 2+).
- `OPEN_WINDOW_STATUS` — terminal window state token (milestone 3).

Tests may rewrite this file at runtime; implementations must read declarations rather than hardcode constants from the shipped sample deck.
