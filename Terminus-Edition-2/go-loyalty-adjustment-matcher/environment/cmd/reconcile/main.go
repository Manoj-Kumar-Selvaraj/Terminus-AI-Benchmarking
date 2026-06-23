package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Accrual struct {
	ID       string
	Member string
	Amount   int
	Status   string
	Reason   string
}

type Adjustment struct {
	AccrualID string
	Member  string
	Amount    int
	Reason    string
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
	accruals, err := loadAccruals("/app/data/accruals.csv")
	if err != nil {
		return err
	}
	adjustments, err := loadAdjustments("/app/data/adjustments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(accruals, adjustments)
}

func loadAccruals(path string) ([]Accrual, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Accrual, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Accrual{ID: row[0], Member: row[1], Amount: amount, Status: row[3], Reason: row[4]})
	}
	return out, nil
}

func loadAdjustments(path string) ([]Adjustment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Adjustment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Adjustment{AccrualID: row[0], Member: row[1], Amount: amount, Reason: row[3]})
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

func writeOutputs(accruals []Accrual, adjustments []Adjustment) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "adjustment_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"accrual_id", "member_id", "reason", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, adjustment := range adjustments {
		match := findMatch(accruals, adjustment)
		reason := ""
		status := "UNMATCHED"
		if match != nil {
			reason = match.Reason
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= adjustment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += adjustment.Amount
		}
		if err := writer.Write([]string{
			adjustment.AccrualID,
			adjustment.Member,
			reason,
			strconv.Itoa(adjustment.Amount),
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
	return os.WriteFile("/app/out/adjustment_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(accruals []Accrual, adjustment Adjustment) *Accrual {
	for i := range accruals {
		accrual := &accruals[i]
		if len(accrual.ID) >= 8 && len(adjustment.AccrualID) >= 8 &&
			accrual.ID[:8] == adjustment.AccrualID[:8] &&
			accrual.Member == adjustment.Member &&
			accrual.Amount == adjustment.Amount &&
			accrual.Status == "POSTED" &&
			allowedReason(accrual.Reason) &&
			accrual.Reason == adjustment.Reason {
			return accrual
		}
	}
	return nil
}

func allowedReason(reason string) bool {
	return reason == "PURCHASE" || reason == "PROMO"
}
