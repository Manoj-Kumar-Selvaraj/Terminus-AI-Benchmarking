package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Rental struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Depot   string
}

type Deposit struct {
	RentalID string
	Customer  string
	Amount    int
	Depot    string
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	rentals, err := loadRentals("/app/data/rentals.csv")
	if err != nil {
		return err
	}
	deposits, err := loadDeposits("/app/data/deposits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(rentals, deposits)
}

func loadRentals(path string) ([]Rental, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Rental, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Rental{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Depot: row[4]})
	}
	return out, nil
}

func loadDeposits(path string) ([]Deposit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Deposit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Deposit{RentalID: row[0], Customer: row[1], Amount: amount, Depot: row[3]})
	}
	return out, nil
}

func readRows(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	return rows[1:], nil
}

func writeOutputs(rentals []Rental, deposits []Deposit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "deposit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"rental_id", "renter_id", "depot", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, deposit := range deposits {
		match := findMatch(rentals, deposit)
		depot := ""
		status := "UNMATCHED"
		if match != nil {
			depot = match.Depot
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= deposit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += deposit.Amount
		}
		if err := writer.Write([]string{
			deposit.RentalID,
			deposit.Customer,
			depot,
			strconv.Itoa(deposit.Amount),
			status,
		}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}

	summaryBytes, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/deposit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(rentals []Rental, deposit Deposit) *Rental {
	for i := range rentals {
		rental := &rentals[i]
		if len(rental.ID) >= 8 && len(deposit.RentalID) >= 8 &&
			rental.ID[:8] == deposit.RentalID[:8] &&
			rental.Customer == deposit.Customer &&
			rental.Amount == deposit.Amount &&
			rental.Status == "RETURNED" &&
			allowedDepot(rental.Depot) &&
			rental.Depot == deposit.Depot {
			return rental
		}
	}
	return nil
}

func allowedDepot(depot string) bool {
	return depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"
}
