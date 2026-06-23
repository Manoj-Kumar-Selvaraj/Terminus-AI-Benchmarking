#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GO'
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

type Lease struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel  string
}

type Deposit struct {
	LeaseID   string
	Customer  string
	Amount    int
	RawAmount string
	Channel   string
	Valid     bool
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
	deposits, err := loadDeposits("/app/data/deposits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(leases, deposits)
}

func loadLeases(path string) ([]Lease, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Lease, 0, len(rows))
	for _, row := range rows {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			continue
		}
		out = append(out, Lease{
			ID:       clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Status:   strings.ToUpper(clean(row[3])),
			Channel:  strings.ToUpper(clean(row[4])),
		})
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
		if len(row) < 4 {
			continue
		}
		rawAmount := clean(row[2])
		amount, err := strconv.Atoi(rawAmount)
		valid := err == nil
		if !valid {
			amount = 0
		}
		out = append(out, Deposit{
			LeaseID:   clean(row[0]),
			Customer:  clean(row[1]),
			Amount:    amount,
			RawAmount: rawAmount,
			Channel:   strings.ToUpper(clean(row[3])),
			Valid:     valid,
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
		return [][]string{}, nil
	}
	return rows[1:], nil
}

func writeOutputs(leases []Lease, deposits []Deposit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportFile, err := os.Create(filepath.Join("/app/out", "deposit_report.csv"))
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"lease_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(leases))
	for _, deposit := range deposits {
		status := "UNMATCHED"
		channel := ""
		match := findMatch(leases, deposit, used)
		if match >= 0 {
			used[match] = true
			status = "MATCHED"
			channel = leases[match].Channel
			summary.MatchedCount++
			summary.MatchedAmountCents += deposit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += deposit.Amount
		}
		amountText := deposit.RawAmount
		if deposit.Valid {
			amountText = strconv.Itoa(deposit.Amount)
		}
		if err := writer.Write([]string{
			deposit.LeaseID,
			deposit.Customer,
			channel,
			amountText,
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

func findMatch(leases []Lease, deposit Deposit, used []bool) int {
	if !deposit.Valid {
		return -1
	}
	for i := range leases {
		if used[i] {
			continue
		}
		lease := &leases[i]
		leaseChannel := strings.ToUpper(clean(lease.Channel))
		depositChannel := strings.ToUpper(clean(deposit.Channel))
		if lease.ID == deposit.LeaseID &&
			lease.Customer == deposit.Customer &&
			lease.Amount == deposit.Amount &&
			strings.ToUpper(clean(lease.Status)) == "POSTED" &&
			allowedChannel(leaseChannel) &&
			leaseChannel == depositChannel {
			return i
		}
	}
	return -1
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "CARD" || channel == "WIRE"
}

func clean(value string) string {
	return strings.TrimSpace(value)
}
GO

/app/scripts/run_batch.sh
test -s /app/out/deposit_report.csv
test -s /app/out/deposit_summary.json
