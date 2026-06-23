package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type holdRow struct {
	holdID, palletID, zoneID, tempBand, amount, holdTS, status, bay string
	consumed                                                          bool
}

type releaseRow struct {
	releaseID, holdID, palletID, zoneID, tempBand, amount, releaseTS, reason, bay string
}

type windowRow struct {
	zoneID, openTS, closeTS, state string
}

func readCSV(path string) []map[string]string {
	file, err := os.Open(path)
	if err != nil {
		panic(err)
	}
	defer file.Close()
	reader := csv.NewReader(file)
	rows, err := reader.ReadAll()
	if err != nil {
		panic(err)
	}
	if len(rows) == 0 {
		return nil
	}
	header := rows[0]
	out := make([]map[string]string, 0, len(rows)-1)
	for _, row := range rows[1:] {
		record := map[string]string{}
		for i, key := range header {
			if i < len(row) {
				record[strings.TrimSpace(key)] = strings.TrimSpace(row[i])
			}
		}
		out = append(out, record)
	}
	return out
}

func isDigits(value string) bool {
	if len(value) != 14 {
		return false
	}
	for _, ch := range value {
		if ch < '0' || ch > '9' {
			return false
		}
	}
	return true
}

// canonicalTempBand maps warehouse shorthand codes before matching.
func canonicalTempBand(raw string) string {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "FZ", "FROZEN":
		return "FROZEN"
	case "CH", "CHILL":
		return "CHILL"
	case "AM", "AMBIENT":
		return "AMBIENT"
	default:
		return strings.ToUpper(strings.TrimSpace(raw))
	}
}

func allowedTempBand(band string) bool {
	return band == "FROZEN" || band == "CHILL"
}

func allowedReason(reason string) bool {
	return reason == "SPOIL" || reason == "QUAR" || reason == "OVERRIDE"
}

func holdMatchesPrefix(holdID, releaseHoldID string) bool {
	return strings.HasPrefix(holdID, releaseHoldID) || strings.HasPrefix(releaseHoldID, holdID)
}

func holdInOpenWindow(hold holdRow, release releaseRow, windows []windowRow) bool {
	if !isDigits(hold.holdTS) || !isDigits(release.releaseTS) {
		return false
	}
	for _, window := range windows {
		if window.zoneID != hold.zoneID {
			continue
		}
		if strings.ToUpper(window.state) != "OPEN" {
			continue
		}
		if !isDigits(window.openTS) || !isDigits(window.closeTS) {
			continue
		}
		if hold.holdTS >= window.openTS && hold.holdTS <= window.closeTS &&
			release.releaseTS >= hold.holdTS && release.releaseTS <= window.closeTS {
			return true
		}
	}
	return false
}

func timestampEligible(hold holdRow, release releaseRow, windows []windowRow) bool {
	return isDigits(hold.holdTS) && isDigits(release.releaseTS) && release.releaseTS >= hold.holdTS
}

func main() {
	holds := make([]holdRow, 0)
	for _, row := range readCSV("/app/data/holds.csv") {
		holds = append(holds, holdRow{
			holdID:   row["hold_id"],
			palletID: row["pallet_id"],
			zoneID:   row["zone_id"],
			tempBand: canonicalTempBand(row["temp_band"]),
			amount:   row["amount"],
			holdTS:   row["hold_ts"],
			status:   row["status"],
			bay:      row["bay"],
		})
	}

	releases := make([]releaseRow, 0)
	for _, row := range readCSV("/app/data/releases.csv") {
		releases = append(releases, releaseRow{
			releaseID: row["release_id"],
			holdID:    row["hold_id"],
			palletID:  row["pallet_id"],
			zoneID:    row["zone_id"],
			tempBand:  canonicalTempBand(row["temp_band"]),
			amount:    row["amount"],
			releaseTS: row["release_ts"],
			reason:    row["reason"],
			bay:       row["bay"],
		})
	}

	windows := make([]windowRow, 0)
	for _, row := range readCSV("/app/config/windows.csv") {
		windows = append(windows, windowRow{
			zoneID:  row["zone_id"],
			openTS:  row["open_ts"],
			closeTS: row["close_ts"],
			state:   row["state"],
		})
	}

	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		panic(err)
	}

	reportPath := filepath.Join("/app/out", "coldchain_release_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		panic(err)
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	_ = writer.Write([]string{"release_id", "hold_id", "pallet_id", "zone_id", "temp_band", "amount", "reason", "status"})

	matchedCount, unmatchedCount := 0, 0
	matchedAmount, unmatchedAmount := 0, 0

	for _, release := range releases {
		releaseBand := release.tempBand
		bestIndex := -1
		for i, hold := range holds {
			if !holdMatchesPrefix(hold.holdID, release.holdID) {
				continue
			}
			if hold.amount != release.amount {
				continue
			}
			if hold.status != "QUARANTINE" {
				continue
			}
			if !allowedTempBand(hold.tempBand) {
				continue
			}
			if hold.tempBand != releaseBand {
				continue
			}
			if !timestampEligible(hold, release, windows) {
				continue
			}
			if bestIndex < 0 || hold.holdTS > holds[bestIndex].holdTS {
				bestIndex = i
			}
		}

		amount, _ := strconv.Atoi(release.amount)
		if bestIndex >= 0 {
			matchedCount++
			matchedAmount -= amount
			_ = writer.Write([]string{
				release.releaseID,
				release.holdID,
				release.palletID,
				release.zoneID,
				releaseBand,
				release.amount,
				release.reason,
				"MATCHED",
			})
		} else {
			unmatchedCount++
			unmatchedAmount += amount
			_ = writer.Write([]string{
				release.releaseID,
				release.holdID,
				release.palletID,
				release.zoneID,
				"",
				release.amount,
				release.reason,
				"UNMATCHED",
			})
		}
	}

	summaryPath := filepath.Join("/app/out", "release_summary.txt")
	summaryBody := fmt.Sprintf(
		"matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n",
		matchedCount, matchedAmount, unmatchedCount, unmatchedAmount,
	)
	if err := os.WriteFile(summaryPath, []byte(summaryBody), 0o644); err != nil {
		panic(err)
	}
}
