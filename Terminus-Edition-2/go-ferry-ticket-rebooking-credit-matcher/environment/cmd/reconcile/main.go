package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Ticket struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	FareType   string
}

type Credit struct {
	TicketID string
	Customer  string
	Amount    int
	FareType    string
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
	tickets, err := loadTickets("/app/data/tickets.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(tickets, credits)
}

func loadTickets(path string) ([]Ticket, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Ticket, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Ticket{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], FareType: row[4]})
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
		out = append(out, Credit{TicketID: row[0], Customer: row[1], Amount: amount, FareType: row[3]})
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

func writeOutputs(tickets []Ticket, credits []Credit) error {
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
	for _, credit := range credits {
		match := findMatch(tickets, credit)
		fare_type := ""
		status := "UNMATCHED"
		if match != nil {
			fare_type = match.FareType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.TicketID,
			credit.Customer,
			fare_type,
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
	return os.WriteFile("/app/out/ticket_credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(tickets []Ticket, credit Credit) *Ticket {
	for i := range tickets {
		ticket := &tickets[i]
		if len(ticket.ID) >= 8 && len(credit.TicketID) >= 8 &&
			ticket.ID[:8] == credit.TicketID[:8] &&
			ticket.Customer == credit.Customer &&
			ticket.Amount == credit.Amount &&
			ticket.Status == "ACTIVE" &&
			allowedFareType(ticket.FareType) &&
			ticket.FareType == credit.FareType {
			return ticket
		}
	}
	return nil
}

func allowedFareType(fare_type string) bool {
	return fare_type == "ECON" || fare_type == "BIKE" || fare_type == "CABIN"
}
