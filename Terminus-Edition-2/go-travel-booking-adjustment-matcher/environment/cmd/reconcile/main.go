package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Booking struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel   string
}

type Adjustment struct {
	BookingID string
	Customer  string
	Amount    int
	Channel    string
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
	bookings, err := loadBookings("/app/data/bookings.csv")
	if err != nil {
		return err
	}
	adjustments, err := loadAdjustments("/app/data/adjustments.csv")
	if err != nil {
		return err
	}
	return writeOutputs(bookings, adjustments)
}

func loadBookings(path string) ([]Booking, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Booking, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Booking{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
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
		out = append(out, Adjustment{BookingID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(bookings []Booking, adjustments []Adjustment) error {
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
	if err := writer.Write([]string{"booking_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, adjustment := range adjustments {
		match := findMatch(bookings, adjustment)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= adjustment.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += adjustment.Amount
		}
		if err := writer.Write([]string{
			adjustment.BookingID,
			adjustment.Customer,
			channel,
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

func findMatch(bookings []Booking, adjustment Adjustment) *Booking {
	for i := range bookings {
		booking := &bookings[i]
		if len(booking.ID) >= 8 && len(adjustment.BookingID) >= 8 &&
			booking.ID[:8] == adjustment.BookingID[:8] &&
			booking.Customer == adjustment.Customer &&
			booking.Amount == adjustment.Amount &&
			booking.Status == "POSTED" &&
			allowedChannel(booking.Channel) &&
			booking.Channel == adjustment.Channel {
			return booking
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
