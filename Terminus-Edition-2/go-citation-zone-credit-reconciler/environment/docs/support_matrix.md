# Support Matrix

Allowed credit zones are `STREET`, `GARAGE`, and `LOT`.

Legacy credit zone aliases are:

- `ST` means `STREET`
- `GRG` means `GARAGE`
- `LT` means `LOT`

Credit method eligibility is controlled by `/app/config/methods.csv` when the credit input includes a `credit_method` column. Methods are compared after trimming and case folding. Only rows whose enabled value is `true` make that method eligible.
