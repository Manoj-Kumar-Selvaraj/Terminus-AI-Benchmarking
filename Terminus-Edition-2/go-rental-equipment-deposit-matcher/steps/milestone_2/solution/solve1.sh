#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
text = text.replace('"strconv"', '"strconv"\n\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Rental{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Depot: row[4]})',
    'out = append(out, Rental{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Depot: strings.ToUpper(clean(row[4]))})',
)
text = text.replace(
    'out = append(out, Deposit{RentalID: row[0], Customer: row[1], Amount: amount, Depot: row[3]})',
    'out = append(out, Deposit{RentalID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Depot: strings.ToUpper(clean(row[3]))})',
)
text = text.replace(
    'summary.MatchedAmountCents -= deposit.Amount',
    'summary.MatchedAmountCents += deposit.Amount',
)
text = text.replace(
    'if len(rental.ID) >= 8 && len(deposit.RentalID) >= 8 &&\n\t\t\trental.ID[:8] == deposit.RentalID[:8] &&',
    'if rental.ID == deposit.RentalID &&',
)
text = text.replace(
    'return depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"',
    'return depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"',
)
text = text.replace(
    '\tsummary := Summary{}\n\tfor _, deposit := range deposits {\n\t\tmatch := findMatch(rentals, deposit)',
    '\tsummary := Summary{}\n\tusedRentals := make([]bool, len(rentals))\n\tfor _, deposit := range deposits {\n\t\tmatchIndex := findMatch(rentals, deposit, usedRentals)\n\t\tvar match *Rental\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &rentals[matchIndex]\n\t\t\tusedRentals[matchIndex] = true\n\t\t}',
)
text = text.replace(
    'func findMatch(rentals []Rental, deposit Deposit) *Rental {\n\tfor i := range rentals {\n\t\trental := &rentals[i]\n\t\tif rental.ID == deposit.RentalID &&',
    'func findMatch(rentals []Rental, deposit Deposit, used []bool) int {\n\tfor i := range rentals {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\trental := &rentals[i]\n\t\tif rental.ID == deposit.RentalID &&',
)
text = text.replace(
    '\t\t\treturn rental\n\t\t}\n\t}\n\treturn nil\n}',
    '\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}',
)
text = text.replace(
    'func allowedDepot(depot string) bool {\n\treturn depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"\n}',
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedDepot(depot string) bool {\n\tdepot = strings.ToUpper(clean(depot))\n\treturn depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"\n}',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/deposit_report.csv
test -s /app/out/deposit_summary.json
