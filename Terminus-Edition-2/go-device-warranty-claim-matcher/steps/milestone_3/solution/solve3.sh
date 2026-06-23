#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Device struct {
	ID           string
	Owner        string
	Amount       int
	Status       string
	Reason       string
	PurchaseDate string
}

type Claim struct {
	DeviceID  string
	Owner     string
	Amount    int
	Reason    string
	ClaimDate string
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
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(devices, claims, openDates)
}

func loadDevices(path string) ([]Device, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Device, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		purchaseDate := ""
		if len(row) > 5 {
			purchaseDate = clean(row[5])
		}
		out = append(out, Device{
			ID:           clean(row[0]),
			Owner:        clean(row[1]),
			Amount:       amount,
			Status:       strings.ToUpper(clean(row[3])),
			Reason:       canonicalReason(row[4]),
			PurchaseDate: purchaseDate,
		})
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
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		claimDate := ""
		if len(row) > 4 {
			claimDate = clean(row[4])
		}
		out = append(out, Claim{
			DeviceID:  clean(row[0]),
			Owner:     clean(row[1]),
			Amount:    amount,
			Reason:    canonicalReason(row[3]),
			ClaimDate: claimDate,
		})
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

func writeOutputs(devices []Device, claims []Claim, openDates map[string]bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportFile, err := os.Create(filepath.Join("/app/out", "warranty_report.csv"))
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
	used := make([]bool, len(devices))
	for _, claim := range claims {
		matchIndex := findMatch(devices, claim, used, openDates)
		reason := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			reason = devices[matchIndex].Reason
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += claim.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += claim.Amount
		}
		if err := writer.Write([]string{claim.DeviceID, claim.Owner, reason, strconv.Itoa(claim.Amount), status}); err != nil {
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

func findMatch(devices []Device, claim Claim, used []bool, openDates map[string]bool) int {
	if !validDate(claim.ClaimDate) || !openDates[claim.ClaimDate] {
		return -1
	}
	best := -1
	for i := range devices {
		if used[i] {
			continue
		}
		device := devices[i]
		if !validDate(device.PurchaseDate) ||
			device.PurchaseDate > claim.ClaimDate ||
			device.ID != claim.DeviceID ||
			device.Owner != claim.Owner ||
			device.Amount != claim.Amount ||
			device.Status != "POSTED" ||
			!allowedReason(device.Reason) ||
			device.Reason != claim.Reason {
			continue
		}
		if best < 0 || device.PurchaseDate > devices[best].PurchaseDate {
			best = i
		}
	}
	return best
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && validDate(fields[0]) && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}

func validDate(value string) bool {
	if value == "" {
		return false
	}
	_, err := time.Parse("2006-01-02", value)
	return err == nil
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalReason(reason string) string {
	switch strings.ToUpper(clean(reason)) {
	case "BAT":
		return "BATTERY"
	case "WTR":
		return "WATER"
	default:
		return strings.ToUpper(clean(reason))
	}
}

func allowedReason(reason string) bool {
	switch canonicalReason(reason) {
	case "SCREEN", "BATTERY", "WATER":
		return true
	default:
		return false
	}
}
GO

/app/scripts/run_batch.sh
test -s /app/out/warranty_report.csv
test -s /app/out/warranty_summary.json
