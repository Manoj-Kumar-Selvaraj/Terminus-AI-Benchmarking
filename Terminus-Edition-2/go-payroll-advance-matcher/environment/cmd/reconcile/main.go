package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Advance struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Method   string
}

type Repayment struct {
	AdvanceID string
	Customer  string
	Amount    int
	Method    string
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
	advances, err := loadAdvances("/app/data/advances.csv")
	if err != nil {
		return err
	}
	repayments, err := loadRepayments("/app/data/repayments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(advances, repayments)
}

func loadAdvances(path string) ([]Advance, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Advance, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Advance{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Method: row[4]})
	}
	return out, nil
}

func loadRepayments(path string) ([]Repayment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Repayment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Repayment{AdvanceID: row[0], Customer: row[1], Amount: amount, Method: row[3]})
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

func writeOutputs(advances []Advance, repayments []Repayment) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "repayment_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"advance_id", "employee_id", "method", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, repayment := range repayments {
		match := findMatch(advances, repayment)
		method := ""
		status := "UNMATCHED"
		if match != nil {
			method = match.Method
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= repayment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += repayment.Amount
		}
		if err := writer.Write([]string{
			repayment.AdvanceID,
			repayment.Customer,
			method,
			strconv.Itoa(repayment.Amount),
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
	return os.WriteFile("/app/out/repayment_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(advances []Advance, repayment Repayment) *Advance {
	for i := range advances {
		advance := &advances[i]
		if len(advance.ID) >= 8 && len(repayment.AdvanceID) >= 8 &&
			advance.ID[:8] == repayment.AdvanceID[:8] &&
			advance.Customer == repayment.Customer &&
			advance.Amount == repayment.Amount &&
			advance.Status == "ACTIVE" &&
			allowedMethod(advance.Method) &&
			advance.Method == repayment.Method {
			return advance
		}
	}
	return nil
}

func allowedMethod(method string) bool {
	return method == "DIRECT" || method == "PAYROLL" || method == "DEBIT"
}
