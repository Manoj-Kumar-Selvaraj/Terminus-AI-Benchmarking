package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Session struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	TrainingType   string
}

type Rebate struct {
	SessionID string
	Customer  string
	Amount    int
	TrainingType    string
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
	sessions, err := loadSessions("/app/data/sessions.csv")
	if err != nil {
		return err
	}
	rebates, err := loadRebates("/app/data/rebates.csv")
	if err != nil {
		return err
	}
	return writeOutputs(sessions, rebates)
}

func loadSessions(path string) ([]Session, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Session, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Session{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], TrainingType: row[4]})
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
		out = append(out, Rebate{SessionID: row[0], Customer: row[1], Amount: amount, TrainingType: row[3]})
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

func writeOutputs(sessions []Session, rebates []Rebate) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "session_rebate_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"session_id", "client_id", "training_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, rebate := range rebates {
		match := findMatch(sessions, rebate)
		training_type := ""
		status := "UNMATCHED"
		if match != nil {
			training_type = match.TrainingType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= rebate.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += rebate.Amount
		}
		if err := writer.Write([]string{
			rebate.SessionID,
			rebate.Customer,
			training_type,
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
	return os.WriteFile("/app/out/session_rebate_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(sessions []Session, rebate Rebate) *Session {
	for i := range sessions {
		session := &sessions[i]
		if len(session.ID) >= 8 && len(rebate.SessionID) >= 8 &&
			session.ID[:8] == rebate.SessionID[:8] &&
			session.Customer == rebate.Customer &&
			session.Amount == rebate.Amount &&
			session.Status == "ACTIVE" &&
			allowedTrainingType(session.TrainingType) &&
			session.TrainingType == rebate.TrainingType {
			return session
		}
	}
	return nil
}

func allowedTrainingType(training_type string) bool {
	return training_type == "SOLO" || training_type == "DUO" || training_type == "TEAM"
}
