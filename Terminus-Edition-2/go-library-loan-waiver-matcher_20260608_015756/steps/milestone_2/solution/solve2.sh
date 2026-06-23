#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/cmd/reconcile/main.go <<'GOEOF'
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Loan struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel  string
}

type Waiver struct {
	LoanID   string
	Customer string
	Amount   int
	Channel  string
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
	loans, err := loadLoans("/app/data/loans.csv")
	if err != nil {
		return err
	}
	waivers, err := loadWaivers("/app/data/waivers.csv")
	if err != nil {
		return err
	}
	return writeOutputs(loans, waivers)
}

func loadLoans(path string) ([]Loan, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Loan, 0, len(rows))
	for _, row := range rows {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		out = append(out, Loan{
			ID:       clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Status:   strings.ToUpper(clean(row[3])),
			Channel:  canonicalChannel(row[4]),
		})
	}
	return out, nil
}

func loadWaivers(path string) ([]Waiver, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Waiver, 0, len(rows))
	for _, row := range rows {
		if len(row) < 4 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		out = append(out, Waiver{
			LoanID:   clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Channel:  canonicalChannel(row[3]),
		})
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

func writeOutputs(loans []Loan, waivers []Waiver) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "waiver_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"loan_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	usedLoans := make([]bool, len(loans))
	for _, waiver := range waivers {
		matchIndex := findMatch(loans, waiver, usedLoans)
		channel := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			usedLoans[matchIndex] = true
			channel = loans[matchIndex].Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += waiver.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += waiver.Amount
		}
		if err := writer.Write([]string{waiver.LoanID, waiver.Customer, channel, strconv.Itoa(waiver.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/waiver_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(loans []Loan, waiver Waiver, used []bool) int {
	for i := range loans {
		if used[i] {
			continue
		}
		loan := loans[i]
		if loan.ID == waiver.LoanID &&
			loan.Customer == waiver.Customer &&
			loan.Amount == waiver.Amount &&
			loan.Status == "POSTED" &&
			allowedChannel(loan.Channel) &&
			loan.Channel == waiver.Channel {
			return i
		}
	}
	return -1
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalChannel(channel string) string {
	switch strings.ToUpper(clean(channel)) {
	case "CC":
		return "CARD"
	case "WIR":
		return "WIRE"
	default:
		return strings.ToUpper(clean(channel))
	}
}

func allowedChannel(channel string) bool {
	channel = canonicalChannel(channel)
	return channel == "ACH" || channel == "CARD" || channel == "WIRE"
}
GOEOF

/usr/local/go/bin/gofmt -w /app/cmd/reconcile/main.go
/app/scripts/run_batch.sh
test -s /app/out/waiver_report.csv
test -s /app/out/waiver_summary.json
