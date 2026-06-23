# Support Matrix

Allowed waiver plans are `BASIC`, `PLUS`, and `ELITE`.

Legacy waiver plan aliases are:

- `BAS` means `BASIC`
- `PLU` means `PLUS`
- `ELI` means `ELITE`

Waiver method eligibility is controlled by `/app/config/methods.csv` when the waiver input includes a `waiver_method` column. Methods are compared after trimming and case folding. Only rows whose enabled value is `true` make that method eligible.
