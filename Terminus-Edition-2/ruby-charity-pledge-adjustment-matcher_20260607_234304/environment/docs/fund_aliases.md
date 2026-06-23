# Fund aliases

Legacy adjustment exports may use short fund codes. Normalize before matching:

| Alias | Canonical |
|-------|-----------|
| `GEN` | `GENERAL` |
| `CAP` | `CAPITAL` |
| `REL` | `RELIEF` |

Aliases are case-insensitive and should be trimmed. The canonical value is written to matched report rows. The authoritative map lives in `/app/config/fund_aliases.json`; enabled funds are listed in `/app/config/methods.csv`.
