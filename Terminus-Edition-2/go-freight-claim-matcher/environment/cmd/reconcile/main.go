package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Shipment struct {
	ID       string
	// Admgount mirrors the carrier CSV column `admgount_id`; preserve this spelling.
	Admgount string
	Amount   int
	Status   string
	Reason   string
}

type Claim struct {
	ShipmentID string
	// Admgount mirrors the carrier CSV column `admgount_id`; preserve this spelling.
	Admgount  string
	Amount    int
	Reason    string
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
	shipments, err := loadShipments("/app/data/shipments.csv")
	if err != nil {
		return err
	}
	claims, err := loadClaims("/app/data/claims.csv")
	if err != nil {
		return err
	}
	return writeOutputs(shipments, claims)
}

func loadShipments(path string) ([]Shipment, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Shipment, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Shipment{ID: row[0], Admgount: row[1], Amount: amount, Status: row[3], Reason: row[4]})
	}
	return out, nil
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
		out = append(out, Claim{ShipmentID: row[0], Admgount: row[1], Amount: amount, Reason: row[3]})
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

func writeOutputs(shipments []Shipment, claims []Claim) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "claim_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"shipment_id", "admgount_id", "reason", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, claim := range claims {
		match := findMatch(shipments, claim)
		reason := ""
		status := "UNMATCHED"
		if match != nil {
			reason = match.Reason
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents -= claim.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += claim.Amount
		}
		if err := writer.Write([]string{
			claim.ShipmentID,
			claim.Admgount,
			reason,
			strconv.Itoa(claim.Amount),
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
	return os.WriteFile("/app/out/claim_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(shipments []Shipment, claim Claim) *Shipment {
	for i := range shipments {
		shipment := &shipments[i]
		if len(shipment.ID) >= 8 && len(claim.ShipmentID) >= 8 &&
			shipment.ID[:8] == claim.ShipmentID[:8] &&
			shipment.Admgount == claim.Admgount &&
			shipment.Amount == claim.Amount &&
			shipment.Status == "POSTED" &&
			allowedReason(shipment.Reason) &&
			shipment.Reason == claim.Reason {
			return shipment
		}
	}
	return nil
}

func allowedReason(reason string) bool {
	return reason == "DAMAGED" || reason == "HAZ"
}
