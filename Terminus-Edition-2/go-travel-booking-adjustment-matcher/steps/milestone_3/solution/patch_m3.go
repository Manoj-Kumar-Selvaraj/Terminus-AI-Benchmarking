//go:build ignore

package main

import (
	"os"
	"regexp"
	"strings"
)

func main() {
	path := "/app/cmd/reconcile/main.go"
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	text := string(data)
	if strings.Contains(text, "openDates map[string]bool") {
		return
	}

	if !strings.Contains(text, "DueDate  string") {
		bookingRe := regexp.MustCompile(`(?s)type Booking struct \{[^}]+\}`)
		text = bookingRe.ReplaceAllString(text, "type Booking struct {\n\tID          string\n\tCustomer    string\n\tAmount      int\n\tStatus      string\n\tChannel     string\n\tDueDate     string\n\tHasDueDate  bool\n}")
		adjustmentRe := regexp.MustCompile(`(?s)type Adjustment struct \{[^}]+\}`)
		text = adjustmentRe.ReplaceAllString(text, "type Adjustment struct {\n\tBookingID         string\n\tCustomer          string\n\tAmount            int\n\tChannel           string\n\tAdjustmentDate    string\n\tHasAdjustmentDate bool\n}")
	}

	text = strings.Replace(text,
		"out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4])})",
		`hasDueDate := len(row) > 5
		dueDate := ""
		if hasDueDate {
			dueDate = clean(row[5])
		}
		out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: canonicalChannel(row[4]), DueDate: dueDate, HasDueDate: hasDueDate})`,
		1,
	)
	text = strings.Replace(text,
		"out = append(out, Adjustment{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3])})",
		`hasAdjustmentDate := len(row) > 4
		adjustmentDate := ""
		if hasAdjustmentDate {
			adjustmentDate = clean(row[4])
		}
		out = append(out, Adjustment{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: canonicalChannel(row[3]), AdjustmentDate: adjustmentDate, HasAdjustmentDate: hasAdjustmentDate})`,
		1,
	)
	text = strings.Replace(text,
		"return writeOutputs(bookings, adjustments)",
		`openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(bookings, adjustments, openDates)`,
		1,
	)
	text = strings.Replace(text,
		"func writeOutputs(bookings []Booking, adjustments []Adjustment) error {",
		"func writeOutputs(bookings []Booking, adjustments []Adjustment, openDates map[string]bool) error {",
		1,
	)
	text = strings.Replace(text,
		"matchIndex := findMatch(bookings, adjustment, usedRecords)",
		"matchIndex := findMatch(bookings, adjustment, usedRecords, openDates)",
		1,
	)

	start := strings.Index(text, "func findMatch(")
	end := strings.Index(text, "\nfunc clean(")
	if start < 0 || end < 0 || end <= start {
		panic("findMatch or clean anchor not found")
	}
	findMatchBlock := `func findMatch(bookings []Booking, adjustment Adjustment, used []bool, openDates map[string]bool) int {
	bestIndex := -1
	for i := range bookings {
		if used[i] {
			continue
		}
		booking := &bookings[i]
		if booking.ID != adjustment.BookingID ||
			booking.Customer != adjustment.Customer ||
			booking.Amount != adjustment.Amount ||
			booking.Status != "POSTED" ||
			!allowedChannel(booking.Channel) ||
			booking.Channel != adjustment.Channel {
			continue
		}
		dateSchemaActive := adjustment.HasAdjustmentDate || booking.HasDueDate
		if dateSchemaActive &&
			(adjustment.AdjustmentDate == "" ||
				booking.DueDate == "" ||
				!openDates[adjustment.AdjustmentDate] ||
				adjustment.AdjustmentDate > booking.DueDate) {
			continue
		}
		if bestIndex < 0 ||
			booking.DueDate > bookings[bestIndex].DueDate ||
			(booking.DueDate == bookings[bestIndex].DueDate && i < bestIndex) {
			bestIndex = i
		}
	}
	return bestIndex
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
`
	text = text[:start] + findMatchBlock + text[end:]

	if err := os.WriteFile(path, []byte(text), 0o644); err != nil {
		panic(err)
	}
}
