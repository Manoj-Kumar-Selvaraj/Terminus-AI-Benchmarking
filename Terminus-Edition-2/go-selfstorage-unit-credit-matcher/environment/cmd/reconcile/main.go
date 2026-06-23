package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Lease struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	UnitType   string
}

type Credit struct {
	LeaseID string
	Customer  string
	Amount    int
	UnitType    string
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
	leases, err := loadLeases("/app/data/leases.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(leases, credits)
}

func loadLeases(path string) ([]Lease, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Lease, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Lease{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], UnitType: row[4]})
	}
	return out, nil
}

func loadCredits(path string) ([]Credit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Credit{LeaseID: row[0], Customer: row[1], Amount: amount, UnitType: row[3]})
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

func writeOutputs(leases []Lease, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"lease_id", "tenant_id", "unit_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(leases, credit)
		unit_type := ""
		status := "UNMATCHED"
		if match != nil {
			unit_type = match.UnitType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.LeaseID,
			credit.Customer,
			unit_type,
			strconv.Itoa(credit.Amount),
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
	return os.WriteFile("/app/out/credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(leases []Lease, credit Credit) *Lease {
	for i := range leases {
		lease := &leases[i]
		if len(lease.ID) >= 8 && len(credit.LeaseID) >= 8 &&
			lease.ID[:8] == credit.LeaseID[:8] &&
			lease.Customer == credit.Customer &&
			lease.Amount == credit.Amount &&
			lease.Status == "ACTIVE" &&
			allowedUnitType(lease.UnitType) &&
			lease.UnitType == credit.UnitType {
			return lease
		}
	}
	return nil
}

func allowedUnitType(unit_type string) bool {
	return unit_type == "SMALL" || unit_type == "MEDIUM" || unit_type == "LARGE"
}
