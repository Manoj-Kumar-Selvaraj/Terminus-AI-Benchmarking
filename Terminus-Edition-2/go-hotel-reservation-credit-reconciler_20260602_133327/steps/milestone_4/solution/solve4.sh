#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GOEOF'
package main

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

const (
	sourcePath   = "/app/data/reservations.csv"
	actionsPath  = "/app/data/credits.csv"
	reportPath   = "/app/out/credit_report.csv"
	summaryPath  = "/app/out/credit_summary.json"
	calendarPath = "/app/config/cutoff_calendar.txt"
	methodsPath  = "/app/config/methods.csv"
)

type Reservation struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel  string
	DueDate  string
}

type Credit struct {
	ReservationID string
	Customer      string
	Amount        int
	Channel       string
	CreditDate    string
}

type ChannelEntry struct {
	Enabled  bool
	Priority int
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func clean(v string) string { return strings.TrimSpace(v) }

func canonicalChannel(v string) string {
	switch strings.ToUpper(clean(v)) {
	case "CC":
		return "CARD"
	case "WIR":
		return "WIRE"
	default:
		return strings.ToUpper(clean(v))
	}
}

func loadPolicy() map[string]ChannelEntry {
	defaults := []string{"ACH", "CARD", "WIRE"}
	fallback := func() map[string]ChannelEntry {
		p := map[string]ChannelEntry{}
		for i, ch := range defaults {
			p[ch] = ChannelEntry{Enabled: true, Priority: i + 1}
		}
		return p
	}
	f, err := os.Open(methodsPath)
	if err != nil {
		return fallback()
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil || len(rows) <= 1 {
		return fallback()
	}
	policy := map[string]ChannelEntry{}
	for idx, row := range rows[1:] {
		if len(row) < 2 {
			continue
		}
		ch := canonicalChannel(row[0])
		if ch == "" {
			continue
		}
		enabled := strings.EqualFold(clean(row[1]), "true")
		priority := 10000 + idx
		if len(row) >= 3 {
			if p, e := strconv.Atoi(clean(row[2])); e == nil {
				priority = p
			}
		}
		policy[ch] = ChannelEntry{Enabled: enabled, Priority: priority}
	}
	if len(policy) == 0 {
		return fallback()
	}
	return policy
}

func enabledChannel(ch string, policy map[string]ChannelEntry) bool {
	e, ok := policy[ch]
	return ok && e.Enabled
}

func channelPriority(ch string, policy map[string]ChannelEntry) int {
	if e, ok := policy[ch]; ok {
		return e.Priority
	}
	return 99999
}

func loadOpenDates() (map[string]bool, error) {
	f, err := os.Open(calendarPath)
	if err != nil {
		return map[string]bool{}, nil
	}
	defer f.Close()
	dates := map[string]bool{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		fields := strings.Fields(sc.Text())
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			dates[fields[0]] = true
		}
	}
	return dates, sc.Err()
}

func readCSV(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	return r.ReadAll()
}

func dateMode(rsvRows, crdRows [][]string) bool {
	check := func(rows [][]string, col string) bool {
		if len(rows) == 0 {
			return false
		}
		for _, h := range rows[0] {
			if strings.EqualFold(clean(h), col) {
				return true
			}
		}
		return false
	}
	return check(rsvRows, "due_date") || check(crdRows, "credit_date")
}

func loadReservations(rows [][]string, dated bool) ([]Reservation, error) {
	out := make([]Reservation, 0)
	for _, row := range rows[1:] {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		dueDate := ""
		if dated && len(row) > 5 {
			dueDate = clean(row[5])
		}
		out = append(out, Reservation{
			ID:       clean(row[0]),
			Customer: clean(row[1]),
			Amount:   amount,
			Status:   strings.ToUpper(clean(row[3])),
			Channel:  canonicalChannel(row[4]),
			DueDate:  dueDate,
		})
	}
	return out, nil
}

func loadCredits(rows [][]string, dated bool) ([]Credit, error) {
	out := make([]Credit, 0)
	for _, row := range rows[1:] {
		if len(row) < 4 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		creditDate := ""
		if dated && len(row) > 4 {
			creditDate = clean(row[4])
		}
		out = append(out, Credit{
			ReservationID: clean(row[0]),
			Customer:      clean(row[1]),
			Amount:        amount,
			Channel:       canonicalChannel(row[3]),
			CreditDate:    creditDate,
		})
	}
	return out, nil
}

func betterCandidate(rsv, best Reservation, idx, bestIdx int, policy map[string]ChannelEntry) bool {
	if rsv.DueDate != best.DueDate {
		return rsv.DueDate > best.DueDate
	}
	p1 := channelPriority(rsv.Channel, policy)
	p2 := channelPriority(best.Channel, policy)
	if p1 != p2 {
		return p1 < p2
	}
	return idx < bestIdx
}

func findMatch(reservations []Reservation, credit Credit, used []bool, openDates map[string]bool, dated bool, policy map[string]ChannelEntry) int {
	bestIndex := -1
	for i, rsv := range reservations {
		if used[i] {
			continue
		}
		if rsv.ID != credit.ReservationID {
			continue
		}
		if rsv.Customer != credit.Customer {
			continue
		}
		if rsv.Amount != credit.Amount {
			continue
		}
		if rsv.Status != "POSTED" {
			continue
		}
		if !enabledChannel(rsv.Channel, policy) {
			continue
		}
		if credit.Channel != "ANY" {
			if !enabledChannel(credit.Channel, policy) {
				continue
			}
			if rsv.Channel != credit.Channel {
				continue
			}
		}
		if dated {
			if rsv.DueDate == "" || credit.CreditDate == "" {
				continue
			}
			if !openDates[credit.CreditDate] {
				continue
			}
			if credit.CreditDate > rsv.DueDate {
				continue
			}
		}
		if bestIndex < 0 {
			bestIndex = i
		} else if dated || credit.Channel == "ANY" {
			if betterCandidate(rsv, reservations[bestIndex], i, bestIndex, policy) {
				bestIndex = i
			}
		}
	}
	return bestIndex
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	rsvRows, err := readCSV(sourcePath)
	if err != nil {
		return err
	}
	crdRows, err := readCSV(actionsPath)
	if err != nil {
		return err
	}
	dated := dateMode(rsvRows, crdRows)
	reservations, err := loadReservations(rsvRows, dated)
	if err != nil {
		return err
	}
	credits, err := loadCredits(crdRows, dated)
	if err != nil {
		return err
	}
	policy := loadPolicy()
	openDates, err := loadOpenDates()
	if err != nil {
		return err
	}
	used := make([]bool, len(reservations))
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	f, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	if err := w.Write([]string{"reservation_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}
	summary := Summary{}
	for _, credit := range credits {
		idx := findMatch(reservations, credit, used, openDates, dated, policy)
		if idx >= 0 {
			used[idx] = true
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
			if err := w.Write([]string{
				credit.ReservationID,
				credit.Customer,
				reservations[idx].Channel,
				strconv.Itoa(credit.Amount),
				"MATCHED",
			}); err != nil {
				return err
			}
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
			if err := w.Write([]string{
				credit.ReservationID,
				credit.Customer,
				"",
				strconv.Itoa(credit.Amount),
				"UNMATCHED",
			}); err != nil {
				return err
			}
		}
	}
	if w.Error() != nil {
		return w.Error()
	}
	b, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(summaryPath, append(b, '\n'), 0o644)
}
GOEOF

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
