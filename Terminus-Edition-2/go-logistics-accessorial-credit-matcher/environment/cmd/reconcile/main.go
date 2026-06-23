package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Charge struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Mode   string
}

type Credit struct {
	ChargeID string
	Customer  string
	Amount    int
	Mode    string
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
	charges, err := loadCharges("/app/data/charges.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(charges, credits)
}

func loadCharges(path string) ([]Charge, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Charge, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Charge{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Mode: row[4]})
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
		out = append(out, Credit{ChargeID: row[0], Customer: row[1], Amount: amount, Mode: row[3]})
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

func writeOutputs(charges []Charge, credits []Credit) error {
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
	if err := writer.Write([]string{"charge_id", "shipper_id", "mode", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(charges, credit)
		mode := ""
		status := "UNMATCHED"
		if match != nil {
			mode = match.Mode
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.ChargeID,
			credit.Customer,
			mode,
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

func findMatch(charges []Charge, credit Credit) *Charge {
	for i := range charges {
		charge := &charges[i]
		if len(charge.ID) >= 8 && len(credit.ChargeID) >= 8 &&
			charge.ID[:8] == credit.ChargeID[:8] &&
			charge.Customer == credit.Customer &&
			charge.Amount == credit.Amount &&
			charge.Status == "BILLED" &&
			allowedMode(charge.Mode) &&
			charge.Mode == credit.Mode {
			return charge
		}
	}
	return nil
}

func allowedMode(mode string) bool {
	return mode == "LTL" || mode == "FTL" || mode == "RAIL"
}
