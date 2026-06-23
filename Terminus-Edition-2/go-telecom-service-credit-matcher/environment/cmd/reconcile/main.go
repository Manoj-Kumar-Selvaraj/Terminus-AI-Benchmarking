package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Service struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel   string
}

type Credit struct {
	ServiceID string
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
	services, err := loadServices("/app/data/services.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(services, credits)
}

func loadServices(path string) ([]Service, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Service, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Service{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Channel: row[4]})
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
		out = append(out, Credit{ServiceID: row[0], Customer: row[1], Amount: amount, Channel: row[3]})
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

func writeOutputs(services []Service, credits []Credit) error {
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
	if err := writer.Write([]string{"service_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(services, credit)
		channel := ""
		status := "UNMATCHED"
		if match != nil {
			channel = match.Channel
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.ServiceID,
			credit.Customer,
			channel,
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

func findMatch(services []Service, credit Credit) *Service {
	for i := range services {
		service := &services[i]
		if len(service.ID) >= 8 && len(credit.ServiceID) >= 8 &&
			service.ID[:8] == credit.ServiceID[:8] &&
			service.Customer == credit.Customer &&
			service.Amount == credit.Amount &&
			service.Status == "POSTED" &&
			allowedChannel(service.Channel) &&
			service.Channel == credit.Channel {
			return service
		}
	}
	return nil
}

func allowedChannel(channel string) bool {
	return channel == "ACH" || channel == "WIRE"
}
