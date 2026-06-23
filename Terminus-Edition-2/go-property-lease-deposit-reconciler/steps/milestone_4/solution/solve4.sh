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
	ID      string
	Customer string
	Amount  int
	Status  string
	Channel string
	DueDate string
	Row     int
}

type Deposit struct {
	LeaseID     string
	Customer    string
	Amount      int
	Channel     string
	DepositDate string
}

type Method struct {
	Enabled  bool
	Priority int
}

type Limit struct {
	Customer  string
	Channel   string
	Effective string
	Max       int
	Row       int
}

type Blackout struct {
	Channel string
	Start   string
	End     string
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
	leases, dated, err := loadLeases("/app/data/leases.csv")
	if err != nil {
		return err
	}
	deposits, depositDated, err := loadDeposits("/app/data/deposits.csv")
	if err != nil {
		return err
	}
	dated = dated || depositDated
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil {
		return err
	}
	limits, err := loadLimits("/app/config/customer_limits.csv")
	if err != nil {
		return err
	}
	blackouts, err := loadBlackouts("/app/config/blackouts.csv")
	if err != nil {
		return err
	}
	return writeOutputs(leases, deposits, dated, openDates, methods, limits, blackouts)
}

func loadLeases(path string) ([]Lease, bool, error) {
	records, headers, err := readRecords(path)
	if err != nil {
		return nil, false, err
	}
	dated := hasHeader(headers, "due_date")
	out := make([]Lease, 0, len(records))
	for i, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			return nil, false, err
		}
		out = append(out, Lease{
			ID: clean(row["lease_id"]), Customer: clean(row["customer_id"]), Amount: amount,
			Status: strings.ToUpper(clean(row["status"])), Channel: canonicalChannel(row["channel"]),
			DueDate: clean(row["due_date"]), Row: i,
		})
	}
	return out, dated, nil
}

func loadDeposits(path string) ([]Deposit, bool, error) {
	records, headers, err := readRecords(path)
	if err != nil {
		return nil, false, err
	}
	dated := hasHeader(headers, "deposit_date")
	out := make([]Deposit, 0, len(records))
	for _, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			return nil, false, err
		}
		out = append(out, Deposit{
			LeaseID: clean(row["lease_id"]), Customer: clean(row["customer_id"]), Amount: amount,
			Channel: canonicalChannel(row["channel"]), DepositDate: clean(row["deposit_date"]),
		})
	}
	return out, dated, nil
}

func readRecords(path string) ([]map[string]string, []string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, nil, err
	}
	if len(rows) == 0 {
		return nil, nil, nil
	}
	headers := rows[0]
	out := make([]map[string]string, 0, len(rows)-1)
	for _, row := range rows[1:] {
		rec := map[string]string{}
		for i, header := range headers {
			if i < len(row) {
				rec[clean(header)] = row[i]
			}
		}
		out = append(out, rec)
	}
	return out, headers, nil
}

func writeOutputs(leases []Lease, deposits []Deposit, dated bool, openDates map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
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

	used := make([]bool, len(leases))
	budget := map[string]int{}
	summary := Summary{}
	for _, deposit := range deposits {
		matchIndex := findMatch(leases, deposit, used, dated, openDates, methods, limits, blackouts, budget)
		channel := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			lease := leases[matchIndex]
			used[matchIndex] = true
			channel = lease.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += deposit.Amount
			if dated {
				budget[budgetKey(deposit, lease.Channel)] += deposit.Amount
			}
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += deposit.Amount
		}
		if err := writer.Write([]string{deposit.LeaseID, deposit.Customer, channel, strconv.Itoa(deposit.Amount), status}); err != nil {
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

func findMatch(leases []Lease, deposit Deposit, used []bool, dated bool, openDates map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i := range leases {
		lease := leases[i]
		if used[i] || !eligible(lease, deposit, dated, openDates, methods, limits, blackouts, budget) {
			continue
		}
		if best < 0 || betterCandidate(lease, leases[best], deposit, dated, methods) {
			best = i
		}
	}
	return best
}

func eligible(lease Lease, deposit Deposit, dated bool, openDates map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if lease.ID != deposit.LeaseID || lease.Customer != deposit.Customer || lease.Amount != deposit.Amount || lease.Status != "POSTED" {
		return false
	}
	if !allowedChannel(lease.Channel) || !methodEnabled(lease.Channel, methods) {
		return false
	}
	if deposit.Channel == "ANY" {
		// The selected lease channel is used.
	} else if !allowedChannel(deposit.Channel) || deposit.Channel != lease.Channel || !methodEnabled(deposit.Channel, methods) {
		return false
	}
	if !dated {
		return true
	}
	if !dateOK(deposit.DepositDate) || !dateOK(lease.DueDate) || !openDates[deposit.DepositDate] || deposit.DepositDate > lease.DueDate {
		return false
	}
	if blackedOut(lease.Channel, deposit.DepositDate, blackouts) {
		return false
	}
	limit := bestLimit(deposit, lease.Channel, limits)
	if limit == nil || budget[budgetKey(deposit, lease.Channel)]+deposit.Amount > limit.Max {
		return false
	}
	return true
}

func betterCandidate(candidate Lease, current Lease, deposit Deposit, dated bool, methods map[string]Method) bool {
	if dated && candidate.DueDate != current.DueDate {
		return candidate.DueDate > current.DueDate
	}
	if deposit.Channel == "ANY" {
		cp := priority(candidate.Channel, methods)
		op := priority(current.Channel, methods)
		if cp != op {
			return cp < op
		}
	}
	return candidate.Row < current.Row
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		parts := strings.Fields(line)
		if len(parts) >= 2 && dateOK(parts[0]) && strings.EqualFold(parts[1], "open") {
			out[parts[0]] = true
		}
	}
	return out, nil
}

func loadMethods(path string) (map[string]Method, error) {
	records, _, err := readRecords(path)
	if err != nil {
		return nil, err
	}
	out := map[string]Method{}
	for _, row := range records {
		channel := canonicalChannel(row["channel"])
		if !allowedChannel(channel) || !strings.EqualFold(clean(row["enabled"]), "true") {
			continue
		}
		priority := 999999
		if value, err := strconv.Atoi(clean(row["priority"])); err == nil {
			priority = value
		}
		out[channel] = Method{Enabled: true, Priority: priority}
	}
	return out, nil
}

func loadLimits(path string) ([]Limit, error) {
	records, _, err := readRecords(path)
	if err != nil {
		return nil, err
	}
	out := []Limit{}
	for i, row := range records {
		customer := clean(row["customer_id"])
		channel := canonicalChannel(row["channel"])
		effective := clean(row["effective_date"])
		max, err := strconv.Atoi(clean(row["max_daily_amount"]))
		if customer == "" || !allowedChannel(channel) || !dateOK(effective) || err != nil || !strings.EqualFold(clean(row["status"]), "ACTIVE") {
			continue
		}
		out = append(out, Limit{Customer: customer, Channel: channel, Effective: effective, Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	records, _, err := readRecords(path)
	if err != nil {
		return nil, err
	}
	out := []Blackout{}
	for _, row := range records {
		channel := canonicalChannel(row["channel"])
		start := clean(row["start_date"])
		end := clean(row["end_date"])
		if !allowedChannel(channel) || !dateOK(start) || !dateOK(end) || start > end || !strings.EqualFold(clean(row["state"]), "ACTIVE") {
			continue
		}
		out = append(out, Blackout{Channel: channel, Start: start, End: end})
	}
	return out, nil
}

func bestLimit(deposit Deposit, channel string, limits []Limit) *Limit {
	best := -1
	for i := range limits {
		limit := limits[i]
		if limit.Customer != deposit.Customer || limit.Channel != channel || limit.Effective > deposit.DepositDate {
			continue
		}
		if best < 0 || limit.Effective > limits[best].Effective || (limit.Effective == limits[best].Effective && limit.Row < limits[best].Row) {
			best = i
		}
	}
	if best < 0 {
		return nil
	}
	return &limits[best]
}

func blackedOut(channel, date string, blackouts []Blackout) bool {
	for _, row := range blackouts {
		if row.Channel == channel && row.Start <= date && date <= row.End {
			return true
		}
	}
	return false
}

func budgetKey(deposit Deposit, channel string) string {
	return deposit.Customer + "|" + channel + "|" + deposit.DepositDate
}

func methodEnabled(channel string, methods map[string]Method) bool {
	method, ok := methods[canonicalChannel(channel)]
	return ok && method.Enabled
}

func priority(channel string, methods map[string]Method) int {
	if method, ok := methods[canonicalChannel(channel)]; ok {
		return method.Priority
	}
	return 999999
}

func canonicalChannel(channel string) string {
	switch strings.ToUpper(clean(channel)) {
	case "CC":
		return "CARD"
	case "WIR":
		return "WIRE"
	case "ANY":
		return "ANY"
	default:
		return strings.ToUpper(clean(channel))
	}
}

func allowedChannel(channel string) bool {
	channel = canonicalChannel(channel)
	return channel == "ACH" || channel == "CARD" || channel == "WIRE"
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func hasHeader(headers []string, name string) bool {
	for _, header := range headers {
		if clean(header) == name {
			return true
		}
	}
	return false
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
GO

/app/scripts/run_batch.sh
test -s /app/out/deposit_report.csv
test -s /app/out/deposit_summary.json
