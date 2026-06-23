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
	SeatZone   string
}

type Voucher struct {
	TicketID string
	Customer  string
	Amount    int
	SeatZone    string
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
	vouchers, err := loadVouchers("/app/data/vouchers.csv")
	if err != nil {
		return err
	}
	return writeOutputs(tickets, vouchers)
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
		out = append(out, Ticket{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], SeatZone: row[4]})
	}
	return out, nil
}

func loadVouchers(path string) ([]Voucher, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Voucher, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Voucher{TicketID: row[0], Customer: row[1], Amount: amount, SeatZone: row[3]})
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

func writeOutputs(tickets []Ticket, vouchers []Voucher) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "voucher_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"ticket_id", "patron_id", "seat_zone", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, voucher := range vouchers {
		match := findMatch(tickets, voucher)
		seat_zone := ""
		status := "UNMATCHED"
		if match != nil {
			seat_zone = match.SeatZone
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= voucher.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += voucher.Amount
		}
		if err := writer.Write([]string{
			voucher.TicketID,
			voucher.Customer,
			seat_zone,
			strconv.Itoa(voucher.Amount),
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
	return os.WriteFile("/app/out/voucher_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(tickets []Ticket, voucher Voucher) *Ticket {
	for i := range tickets {
		ticket := &tickets[i]
		if len(ticket.ID) >= 8 && len(voucher.TicketID) >= 8 &&
			ticket.ID[:8] == voucher.TicketID[:8] &&
			ticket.Customer == voucher.Customer &&
			ticket.Amount == voucher.Amount &&
			ticket.Status == "ISSUED" &&
			allowedSeatZone(ticket.SeatZone) &&
			ticket.SeatZone == voucher.SeatZone {
			return ticket
		}
	}
	return nil
}

func allowedSeatZone(seat_zone string) bool {
	return seat_zone == "ORCH" || seat_zone == "MEZZ" || seat_zone == "BALC"
}
