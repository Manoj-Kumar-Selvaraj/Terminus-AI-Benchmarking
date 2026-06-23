package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Workshop struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	WorkshopType   string
}

type Refund struct {
	WorkshopID string
	Customer  string
	Amount    int
	WorkshopType    string
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
	workshops, err := loadWorkshops("/app/data/workshops.csv")
	if err != nil {
		return err
	}
	refunds, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	return writeOutputs(workshops, refunds)
}

func loadWorkshops(path string) ([]Workshop, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Workshop, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Workshop{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], WorkshopType: row[4]})
	}
	return out, nil
}

func loadRefunds(path string) ([]Refund, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Refund, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Refund{WorkshopID: row[0], Customer: row[1], Amount: amount, WorkshopType: row[3]})
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

func writeOutputs(workshops []Workshop, refunds []Refund) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "workshop_refund_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"workshop_id", "attendee_id", "workshop_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, refund := range refunds {
		match := findMatch(workshops, refund)
		workshop_type := ""
		status := "UNMATCHED"
		if match != nil {
			workshop_type = match.WorkshopType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= refund.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
		if err := writer.Write([]string{
			refund.WorkshopID,
			refund.Customer,
			workshop_type,
			strconv.Itoa(refund.Amount),
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
	return os.WriteFile("/app/out/workshop_refund_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(workshops []Workshop, refund Refund) *Workshop {
	for i := range workshops {
		workshop := &workshops[i]
		if len(workshop.ID) >= 8 && len(refund.WorkshopID) >= 8 &&
			workshop.ID[:8] == refund.WorkshopID[:8] &&
			workshop.Customer == refund.Customer &&
			workshop.Amount == refund.Amount &&
			workshop.Status == "ACTIVE" &&
			allowedWorkshopType(workshop.WorkshopType) &&
			workshop.WorkshopType == refund.WorkshopType {
			return workshop
		}
	}
	return nil
}

func allowedWorkshopType(workshop_type string) bool {
	return workshop_type == "BREW" || workshop_type == "ROAST" || workshop_type == "CUP"
}
