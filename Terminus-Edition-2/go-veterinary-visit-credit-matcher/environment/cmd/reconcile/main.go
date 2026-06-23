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

type Visit struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Clinic   string
}

type Credit struct {
	VisitID  string
	Customer string
	Amount   int
	Clinic   string
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
	visits, err := loadVisites("/app/data/visits.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(visits, credits)
}

func loadVisits(path string) ([]Visit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Visit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Visit{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Clinic: row[4]})
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
		out = append(out, Credit{VisitID: row[0], Customer: row[1], Amount: amount, Clinic: row[3]})
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

func writeOutputs(visits []Visit, credits []Credit) error {
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
	if err := writer.Write([]string{"visit_id", "owner_id", "clinic", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(visits, credit)
		clinic := ""
		status := "UNMATCHED"
		if match != nil {
			clinic = match.Clinic
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.VisitID,
			credit.Customer,
			clinic,
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

func findMatch(visits []Visit, credit Credit) *Visit {
	for i := range visits {
		visit := &visits[i]
		if len(visit.ID) >= 8 && len(credit.VisitID) >= 8 &&
			visit.ID[:8] == credit.VisitID[:8] &&
			visit.Customer == credit.Customer &&
			visit.Amount == credit.Amount &&
			visit.Status == "CLOSED" &&
			allowedClinic(visit.Clinic) &&
			visit.Clinic == credit.Clinic {
			return visit
		}
	}
	return nil
}

func allowedClinic(clinic string) bool {
	clinic = strings.ToUpper(strings.TrimSpace(clinic))
	return clinic == "MAIN" || clinic == "MOBILE"
}
