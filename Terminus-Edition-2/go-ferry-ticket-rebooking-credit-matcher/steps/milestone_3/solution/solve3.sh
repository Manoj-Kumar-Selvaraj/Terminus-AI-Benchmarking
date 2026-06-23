#!/usr/bin/env bash
set -euo pipefail

cd /app

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

type Ticket struct {
	ID         string
	Rider      string
	Amount     int
	Status     string
	FareType string
	VisitDate  string
}

type Credit struct {
	TicketID     string
	Rider      string
	Amount     int
	FareType string
	CreditDate string
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
	ticketHeader, ticketRows, err := readCSV("/app/data/tickets.csv")
	if err != nil {
		return err
	}
	creditHeader, creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		return err
	}
	dated := has(ticketHeader, "travel_date") && has(creditHeader, "credit_date")
	tickets, err := loadTickets(ticketRows, dated)
	if err != nil {
		return err
	}
	credits, err := loadCredits(creditRows, dated)
	if err != nil {
		return err
	}
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil {
			return err
		}
	}
	return writeOutputs(tickets, credits, openDates, dated)
}

func readCSV(path string) ([]string, [][]string, error) {
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
	return rows[0], rows[1:], nil
}

func loadTickets(rows [][]string, dated bool) ([]Ticket, error) {
	out := make([]Ticket, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		ticket := Ticket{ID: clean(row[0]), Rider: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), FareType: canonicalFareType(row[4])}
		if dated && len(row) > 5 {
			ticket.VisitDate = clean(row[5])
		}
		out = append(out, ticket)
	}
	return out, nil
}

func loadCredits(rows [][]string, dated bool) ([]Credit, error) {
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		credit := Credit{TicketID: clean(row[0]), Rider: clean(row[1]), Amount: amount, FareType: canonicalFareType(row[3])}
		if dated && len(row) > 4 {
			credit.CreditDate = clean(row[4])
		}
		out = append(out, credit)
	}
	return out, nil
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

func writeOutputs(tickets []Ticket, credits []Credit, openDates map[string]bool, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "ticket_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"ticket_id", "rider_id", "fare_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(tickets))
	for _, credit := range credits {
		matchIndex := findMatch(tickets, credit, used, openDates, dated)
		accessType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			accessType = tickets[matchIndex].FareType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.TicketID, credit.Rider, accessType, strconv.Itoa(credit.Amount), status}); err != nil {
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
	return os.WriteFile("/app/out/ticket_credit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(tickets []Ticket, credit Credit, used []bool, openDates map[string]bool, dated bool) int {
	best := -1
	for i := range tickets {
		if used[i] {
			continue
		}
		ticket := tickets[i]
		if !eligible(ticket, credit, openDates, dated) {
			continue
		}
		if !dated {
			return i
		}
		if best < 0 || ticket.VisitDate > tickets[best].VisitDate || (ticket.VisitDate == tickets[best].VisitDate && i < best) {
			best = i
		}
	}
	return best
}

func eligible(ticket Ticket, credit Credit, openDates map[string]bool, dated bool) bool {
	if ticket.ID != credit.TicketID || ticket.Rider != credit.Rider || ticket.Amount != credit.Amount || ticket.Status != "ACTIVE" || !allowedFareType(ticket.FareType) || ticket.FareType != credit.FareType {
		return false
	}
	if dated {
		if credit.CreditDate == "" || ticket.VisitDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > ticket.VisitDate {
			return false
		}
	}
	return true
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalFareType(accessType string) string {
	switch strings.ToUpper(clean(accessType)) {
	case "EC":
		return "ECON"
	case "BK":
		return "BIKE"
	case "CB":
		return "CABIN"
	default:
		return strings.ToUpper(clean(accessType))
	}
}

func allowedFareType(accessType string) bool {
	accessType = canonicalFareType(accessType)
	return accessType == "ECON" || accessType == "BIKE" || accessType == "CABIN"
}

func has(headers []string, name string) bool {
	for _, header := range headers {
		if strings.EqualFold(clean(header), name) {
			return true
		}
	}
	return false
}
GO

/app/scripts/run_batch.sh
test -s /app/out/ticket_credit_report.csv
test -s /app/out/ticket_credit_summary.json