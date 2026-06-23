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
	ID         string
	Customer   string
	Amount     int
	Status     string
	Channel    string
	DueDate    string
	HasDueDate bool
}

type Deposit struct {
	LeaseID        string
	Customer       string
	Amount         int
	Channel        string
	DepositDate    string
	HasDepositDate bool
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
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(leases, deposits, openDates)
}

func loadLeases(path string) ([]Lease, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	leases := make([]Lease, 0, len(rows))
	for _, row := range rows {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			continue
		}
		lease := Lease{
			ID:       clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Status:   strings.ToUpper(clean(row[3])),
			Channel:  canonicalChannel(row[4], false),
		}
		if len(row) > 5 {
			lease.HasDueDate = true
			lease.DueDate = clean(row[5])
		}
		leases = append(leases, lease)
	}
	return leases, nil
}

func loadDeposits(path string) ([]Deposit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	deposits := make([]Deposit, 0, len(rows))
	for _, row := range rows {
		if len(row) < 4 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			continue
		}
		deposit := Deposit{
			LeaseID:  clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Channel:  canonicalChannel(row[3], false),
		}
		if len(row) > 4 {
			deposit.HasDepositDate = true
			deposit.DepositDate = clean(row[4])
		}
		deposits = append(deposits, deposit)
	}
	return deposits, nil
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
	if len(rows) <= 1 {
		return [][]string{}, nil
	}
	return rows[1:], nil
}

func writeOutputs(leases []Lease, deposits []Deposit, openDates map[string]bool) error {
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
		match := findMatch(leases, deposit, used, openDates)
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
		if err := writer.Write([]string{
			deposit.LeaseID,
			deposit.Customer,
			channel,
			strconv.Itoa(deposit.Amount),
			status,
		}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}
	data, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/deposit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(leases []Lease, deposit Deposit, used []bool, openDates map[string]bool) int {
	best := -1
	for i := range leases {
		if used[i] {
			continue
		}
		lease := leases[i]
		if lease.ID != deposit.LeaseID ||
			lease.Customer != deposit.Customer ||
			lease.Amount != deposit.Amount ||
			lease.Status != "POSTED" ||
			!validChannel(lease.Channel) ||
			lease.Channel != deposit.Channel {
			continue
		}
		if dateMode(&lease, &deposit) {
			if deposit.DepositDate == "" ||
				lease.DueDate == "" ||
				!dateOK(deposit.DepositDate) ||
				!dateOK(lease.DueDate) ||
				!openDates[deposit.DepositDate] ||
				deposit.DepositDate > lease.DueDate {
				continue
			}
		}
		if best < 0 || lease.DueDate > leases[best].DueDate || (lease.DueDate == leases[best].DueDate && i < best) {
			best = i
		}
	}
	return best
}

func dateMode(lease *Lease, deposit *Deposit) bool {
	return lease.HasDueDate || deposit.HasDepositDate
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}

func canonicalChannel(value string, allowAny bool) string {
	channel := strings.ToUpper(clean(value))
	switch channel {
	case "CC":
		return "CARD"
	case "WIR":
		return "WIRE"
	case "ANY":
		if allowAny {
			return "ANY"
		}
	}
	return channel
}

func validChannel(channel string) bool {
	return channel == "ACH" || channel == "CARD" || channel == "WIRE"
}

func dateOK(value string) bool {
	value = clean(value)
	if len(value) != 10 || value[4] != '-' || value[7] != '-' {
		return false
	}
	for i, ch := range value {
		if i == 4 || i == 7 {
			continue
		}
		if ch < '0' || ch > '9' {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}
GO

/app/scripts/run_batch.sh
test -s /app/out/deposit_report.csv
test -s /app/out/deposit_summary.json
