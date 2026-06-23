package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Claim struct {
	ID       string
	Patient string
	Amount   int
	Status   string
	Procedure   string
}

type Credit struct {
	ClaimID string
	Patient  string
	Amount    int
	Procedure    string
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
	claims, err := loadClaims("/app/data/claims.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(claims, credits)
}

func loadClaims(path string) ([]Claim, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Claim, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Claim{ID: row[0], Patient: row[1], Amount: amount, Status: row[3], Procedure: row[4]})
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
		out = append(out, Credit{ClaimID: row[0], Patient: row[1], Amount: amount, Procedure: row[3]})
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

func writeOutputs(claims []Claim, credits []Credit) error {
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
	if err := writer.Write([]string{"claim_id", "patient_id", "procedure", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, credit := range credits {
		match := findMatch(claims, credit)
		procedure := ""
		status := "UNMATCHED"
		if match != nil {
			procedure = match.Procedure
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			credit.ClaimID,
			credit.Patient,
			procedure,
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

func findMatch(claims []Claim, credit Credit) *Claim {
	for i := range claims {
		claim := &claims[i]
		if len(claim.ID) >= 8 && len(credit.ClaimID) >= 8 &&
			claim.ID[:8] == credit.ClaimID[:8] &&
			claim.Patient == credit.Patient &&
			claim.Amount == credit.Amount &&
			claim.Status == "APPROVED" &&
			allowedProcedure(claim.Procedure) &&
			claim.Procedure == credit.Procedure {
			return claim
		}
	}
	return nil
}

func allowedProcedure(procedure string) bool {
	return procedure == "PREVENTIVE" || procedure == "RESTORATIVE" || procedure == "ORTHO"
}
