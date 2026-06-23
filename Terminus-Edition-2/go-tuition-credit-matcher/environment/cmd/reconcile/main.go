package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Enrollment struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Term   string
}

type Credit struct {
	EnrollmentID string
	Customer  string
	Amount    int
	Term    string
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
	enrollments, err := loadEnrollments("/app/data/enrollments.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(enrollments, credits)
}

func loadEnrollments(path string) ([]Enrollment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Enrollment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Enrollment{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], Term: row[4]})
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
		out = append(out, Credit{EnrollmentID: row[0], Customer: row[1], Amount: amount, Term: row[3]})
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

func writeOutputs(enrollments []Enrollment, credits []Credit) error {
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
	if err := writer.Write([]string{"enrollment_id", "student_id", "term", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(enrollments, credit)
		term := ""
		status := "UNMATCHED"
		if match != nil {
			term = match.Term
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.EnrollmentID,
			credit.Customer,
			term,
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

func findMatch(enrollments []Enrollment, credit Credit) *Enrollment {
	for i := range enrollments {
		enrollment := &enrollments[i]
		if len(enrollment.ID) >= 8 && len(credit.EnrollmentID) >= 8 &&
			enrollment.ID[:8] == credit.EnrollmentID[:8] &&
			enrollment.Customer == credit.Customer &&
			enrollment.Amount == credit.Amount &&
			enrollment.Status == "ENROLLED" &&
			allowedTerm(enrollment.Term) &&
			enrollment.Term == credit.Term {
			return enrollment
		}
	}
	return nil
}

func allowedTerm(term string) bool {
	return term == "ONL" || term == "MAIL" || term == "CAMP"
}
