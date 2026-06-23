//go:build ignore

package main

import (
	"os"
	"strings"
)

func main() {
	path := "/app/cmd/reconcile/main.go"
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	text := string(data)
	if strings.Contains(text, "func clean(value string)") {
		return
	}
	if !strings.Contains(text, `"strings"`) {
		text = strings.Replace(text, `"strconv"`, "\"strconv\"\n\t\"strings\"", 1)
	}
	text = strings.Replace(text, "amount, err := strconv.Atoi(row[2])", "amount, err := strconv.Atoi(clean(row[2]))", -1)
	text = strings.Replace(text,
		"out = append(out, Booking{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})",
		"out = append(out, Booking{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), Channel: strings.ToUpper(clean(row[4]))})",
		1,
	)
	text = strings.Replace(text,
		"out = append(out, Adjustment{BookingID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})",
		"out = append(out, Adjustment{BookingID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Channel: strings.ToUpper(clean(row[3]))})",
		1,
	)
	text = strings.Replace(text,
		"summary.MatchedAmountCents -= adjustment.Amount",
		"summary.MatchedAmountCents += adjustment.Amount",
		1,
	)
	text = strings.Replace(text,
		"if len(booking.ID) >= 8 && len(adjustment.BookingID) >= 8 &&\n\t\t\tbooking.ID[:8] == adjustment.BookingID[:8] &&",
		"if booking.ID == adjustment.BookingID &&",
		1,
	)
	text = strings.Replace(text,
		"\tsummary := Summary{}\n\tfor _, adjustment := range adjustments {\n\t\tmatch := findMatch(bookings, adjustment)",
		"\tsummary := Summary{}\n\tusedRecords := make([]bool, len(bookings))\n\tfor _, adjustment := range adjustments {\n\t\tmatchIndex := findMatch(bookings, adjustment, usedRecords)\n\t\tvar match *Booking\n\t\tif matchIndex >= 0 {\n\t\t\tmatch = &bookings[matchIndex]\n\t\t\tusedRecords[matchIndex] = true\n\t\t}",
		1,
	)
	text = strings.Replace(text,
		"func findMatch(bookings []Booking, adjustment Adjustment) *Booking {\n\tfor i := range bookings {\n\t\tbooking := &bookings[i]\n\t\tif booking.ID == adjustment.BookingID &&",
		"func findMatch(bookings []Booking, adjustment Adjustment, used []bool) int {\n\tfor i := range bookings {\n\t\tif used[i] {\n\t\t\tcontinue\n\t\t}\n\t\tbooking := &bookings[i]\n\t\tif booking.ID == adjustment.BookingID &&",
		1,
	)
	text = strings.Replace(text,
		"\t\t\treturn booking\n\t\t}\n\t}\n\treturn nil\n}",
		"\t\t\treturn i\n\t\t}\n\t}\n\treturn -1\n}",
		1,
	)
	text = strings.Replace(text,
		"func allowedChannel(channel string) bool {\n\treturn channel == \"ACH\" || channel == \"WIRE\"\n}",
		"func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == \"ACH\" || channel == \"CARD\" || channel == \"WIRE\"\n}",
		1,
	)
	if err := os.WriteFile(path, []byte(text), 0o644); err != nil {
		panic(err)
	}
}
