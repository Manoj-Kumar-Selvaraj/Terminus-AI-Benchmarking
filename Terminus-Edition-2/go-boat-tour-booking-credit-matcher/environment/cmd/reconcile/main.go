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
	TourType   string
}

type Credit struct {
	BookingID string
	Customer  string
	Amount    int
	TourType    string
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
	bookings, err := loadBookinges("/app/data/bookings.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(bookings, credits)
}

func loadBookinges(path string) ([]Booking, error) {
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
		out = append(out, Booking{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], TourType: row[4]})
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
		out = append(out, Credit{BookingID: row[0], Customer: row[1], Amount: amount, TourType: row[3]})
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

func writeOutputs(bookings []Booking, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"booking_id", "guest_id", "tour_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(bookings, credit)
		tour_type := ""
		status := "UNMATCHED"
		if match != nil {
			tour_type = match.TourType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.BookingID,
			credit.Customer,
			tour_type,
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
	return os.WriteFile("/app/out/credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(bookings []Booking, credit Credit) *Booking {
	for i := range bookings {
		booking := &bookings[i]
		if len(booking.ID) >= 8 && len(credit.BookingID) >= 8 &&
			booking.ID[:8] == credit.BookingID[:8] &&
			booking.Customer == credit.Customer &&
			booking.Amount == credit.Amount &&
			booking.Status == "SAILED" &&
			allowedTourType(booking.TourType) &&
			booking.TourType == credit.TourType {
			return booking
		}
	}
	return nil
}

func allowedTourType(tour_type string) bool {
	return tour_type == "HARBOR" || tour_type == "SUNSET" || tour_type == "WHALE"
}
