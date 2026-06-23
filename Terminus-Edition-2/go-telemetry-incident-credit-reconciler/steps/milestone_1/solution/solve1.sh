#!/bin/bash
set -euo pipefail
cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type playback struct {
	StreamID, AccountID, Severity, Minutes, StartUTC, EndUTC, Status, Region string
	Row  int
	Used bool
}

type credit struct {
	CreditID, StreamID, AccountID, Severity, Minutes, EventUTC, Reason, Region string
}

type winEntry struct {
	Region, WindowUTC, State string
}

func readCSV(path string) ([]map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	header := rows[0]
	out := []map[string]string{}
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, k := range header {
			if i < len(row) {
				m[strings.TrimSpace(k)] = strings.TrimSpace(row[i])
			}
		}
		out = append(out, m)
	}
	return out, nil
}

func numericTS(s string) bool {
	if len(s) != 14 {
		return false
	}
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

func canonicalSeverity(s string) string {
	return strings.ToUpper(strings.TrimSpace(s))
}

func allowedSeverity(s string) bool {
	return s == "CMEDIUM" || s == "LOW" || s == "BROWSER"
}

func eligibleReason(s string) bool {
	return s == "BUFFER" || s == "DUPLICATELICATE" || s == "CREDIT"
}

// M1: no state check — window is eligible if region matches and event_utc is within range
func windowOK(eventUTC, region string, wins []winEntry) bool {
	if !numericTS(eventUTC) {
		return false
	}
	for _, w := range wins {
		if w.Region == region && numericTS(w.WindowUTC) && eventUTC <= w.WindowUTC {
			return true
		}
	}
	return false
}

func main() {
	playbackRows, err := readCSV("/app/data/playbacks.csv")
	if err != nil {
		panic(err)
	}
	creditRows, err := readCSV("/app/data/credits.csv")
	if err != nil {
		panic(err)
	}
	winRows, err := readCSV("/app/config/region_windows.csv")
	if err != nil {
		panic(err)
	}

	playbacks := []playback{}
	for i, row := range playbackRows {
		playbacks = append(playbacks, playback{
			StreamID: row["incident_id"], AccountID: row["severity_id"],
			Severity: canonicalSeverity(row["severity"]), Minutes: row["minutes"],
			StartUTC: row["start_utc"], EndUTC: row["end_utc"],
			Status: row["status"], Region: row["region"], Row: i,
		})
	}
	wins := []winEntry{}
	for _, row := range winRows {
		wins = append(wins, winEntry{Region: row["region"], WindowUTC: row["window_utc"], State: row["state"]})
	}

	os.MkdirAll("/app/out", 0755)
	report, err := os.Create("/app/out/incident_credit_report.csv")
	if err != nil {
		panic(err)
	}
	defer report.Close()
	writer := csv.NewWriter(report)
	defer writer.Flush()
	writer.Write([]string{"credit_id", "incident_id", "severity_id", "severity", "minutes", "reason", "status"})

	matchedCount, unmatchedCount := 0, 0
	matchedMinutes, unmatchedMinutes := 0, 0

	for _, row := range creditRows {
		c := credit{
			CreditID: row["credit_id"], StreamID: row["incident_id"],
			AccountID: row["severity_id"], Severity: canonicalSeverity(row["severity"]),
			Minutes: row["minutes"], EventUTC: row["event_utc"],
			Reason: row["reason"], Region: row["region"],
		}
		matchIdx := -1
		for i, pb := range playbacks {
			if pb.Used || pb.StreamID != c.StreamID || pb.AccountID != c.AccountID ||
				pb.Region != c.Region || pb.Minutes != c.Minutes {
				continue
			}
			if pb.Status != "POSTED" || !allowedSeverity(pb.Severity) || pb.Severity != c.Severity {
				continue
			}
			if !eligibleReason(c.Reason) || !allowedSeverity(c.Severity) {
				continue
			}
			if !windowOK(c.EventUTC, c.Region, wins) {
				continue
			}
			if !numericTS(pb.StartUTC) || !numericTS(pb.EndUTC) || c.EventUTC < pb.EndUTC {
				continue
			}
			matchIdx = i
			break
		}

		minutes, _ := strconv.Atoi(c.Minutes)
		if matchIdx >= 0 {
			playbacks[matchIdx].Used = true
			matchedCount++
			matchedMinutes += minutes
			writer.Write([]string{c.CreditID, c.StreamID, c.AccountID, playbacks[matchIdx].Severity, c.Minutes, c.Reason, "MATCHED"})
		} else {
			unmatchedCount++
			unmatchedMinutes += minutes
			writer.Write([]string{c.CreditID, c.StreamID, c.AccountID, "", c.Minutes, c.Reason, "UNMATCHED"})
		}
	}

	summary := fmt.Sprintf("matched_count=%d\nmatched_minutes=%d\nunmatched_count=%d\nunmatched_minutes=%d\n",
		matchedCount, matchedMinutes, unmatchedCount, unmatchedMinutes)
	if err := os.WriteFile(filepath.Clean("/app/out/incident_credit_summary.txt"), []byte(summary), 0644); err != nil {
		panic(err)
	}
}
GO
/app/scripts/run_batch.sh
