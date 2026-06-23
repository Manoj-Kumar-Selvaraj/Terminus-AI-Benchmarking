package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

type Device struct {
	ID       string
	Owner string
	Amount   int
	Status   string
	Reason   string
}

type Claim struct {
	DeviceID string
	Owner  string
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
	devices, err := loadDevices("/app/data/devices.csv")
	if err != nil {
		return err
	}
	claims, err := loadClaims("/app/data/warranty_claims.csv")
	if err != nil {
		return err
	}
	return writeOutputs(devices, claims)
}

func loadDevices(path string) ([]Device, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Device, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(row[2])
		if err != nil {
			return nil, err
		}
		out = append(out, Device{ID: row[0], Owner: row[1], Amount: amount, Status: row[3], Reason: row[4]})
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
		out = append(out, Claim{DeviceID: row[0], Owner: row[1], Amount: amount, Reason: row[3]})
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

func writeOutputs(devices []Device, claims []Claim) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "warranty_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"device_id", "owner_id", "reason", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	for _, claim := range claims {
		match := findMatch(devices, claim)
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
			claim.DeviceID,
			claim.Owner,
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
	return os.WriteFile("/app/out/warranty_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(devices []Device, claim Claim) *Device {
	for i := range devices {
		device := &devices[i]
		if len(device.ID) >= 8 && len(claim.DeviceID) >= 8 &&
			device.ID[:8] == claim.DeviceID[:8] &&
			device.Owner == claim.Owner &&
			device.Amount == claim.Amount &&
			device.Status == "POSTED" &&
			allowedReason(device.Reason) &&
			device.Reason == claim.Reason {
			return device
		}
	}
	return nil
}

func allowedReason(reason string) bool {
	return reason == "SCREEN" || reason == "WATER"
}
