package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Meter struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel   string
}

type Rebate struct {
	MeterID string
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
	meters, err := loadMeters("/app/data/meters.csv")
	if err != nil {
		return err
	}
	rebates, err := loadRebates("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	return writeOutputs(meters, rebates)
}

func loadMeters(path string) ([]Meter, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Meter, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Meter{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
	}
	return out, nil
}

func loadRebates(path string) ([]Rebate, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Rebate, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Rebate{MeterID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(meters []Meter, rebates []Rebate) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "rebate_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"meter_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, rebate := range rebates {
		match := findMatch(meters, rebate)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= rebate.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
		}
		if err := writer.Write([]string{
			rebate.MeterID,
			rebate.Customer,
			channel,
			strconv.Itoa(rebate.Amount),
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
	return os.WriteFile("/app/out/rebate_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(meters []Meter, rebate Rebate) *Meter {
	for i := range meters {
		meter := &meters[i]
		if len(meter.ID) >= 8 && len(rebate.MeterID) >= 8 &&
			meter.ID[:8] == rebate.MeterID[:8] &&
			meter.Customer == rebate.Customer &&
			meter.Amount == rebate.Amount &&
			meter.Status == "POSTED" &&
			allowedChannel(meter.Channel) &&
			meter.Channel == rebate.Channel {
			return meter
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
