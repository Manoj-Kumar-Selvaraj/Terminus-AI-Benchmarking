#!/bin/bash
set -euo pipefail
cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"sort"
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

type reasonEntry struct {
	Reason   string
	Eligible bool
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
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "MEDIUM", "CMEDIUM":
		return "CMEDIUM"
	case "PHONE", "LOW":
		return "LOW"
	case "WEBAPP", "BROWSER":
		return "BROWSER"
	default:
		return strings.ToUpper(strings.TrimSpace(s))
	}
}

func allowedSeverity(s string) bool {
	return s == "CMEDIUM" || s == "LOW" || s == "BROWSER"
}

func windowOK(eventUTC, region string, wins []winEntry) bool {
	if !numericTS(eventUTC) {
		return false
	}
	for _, w := range wins {
		if w.Region == region && w.State == "OPEN" && numericTS(w.WindowUTC) && eventUTC <= w.WindowUTC {
			return true
		}
	}
	return false
}

func loadReasons(path string) map[string]bool {
	rows, err := readCSV(path)
	if err != nil {
		return map[string]bool{}
	}
	policy := map[string]bool{}
	for _, row := range rows {
		reason := strings.TrimSpace(row["reason"])
		eligible := strings.ToUpper(strings.TrimSpace(row["eligible"])) == "Y"
		policy[reason] = eligible
	}
	return policy
}

func eligibleReason(reason string, policy map[string]bool) bool {
	if len(policy) == 0 {
		return reason == "BUFFER" || reason == "DUPLICATELICATE" || reason == "CREDIT"
	}
	eligible, found := policy[reason]
	return found && eligible
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

	policy := loadReasons("/app/config/reasons.csv")

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

		isAny := c.Reason == "ANY"
		reasonOK := isAny || eligibleReason(c.Reason, policy)
		if !reasonOK {
			minutes, _ := strconv.Atoi(c.Minutes)
			unmatchedCount++
			unmatchedMinutes += minutes
			writer.Write([]string{c.CreditID, c.StreamID, c.AccountID, "", c.Minutes, c.Reason, "UNMATCHED"})
			continue
		}

		candidates := []int{}
		for i, pb := range playbacks {
			if pb.Used || pb.StreamID != c.StreamID || pb.AccountID != c.AccountID ||
				pb.Region != c.Region || pb.Minutes != c.Minutes {
				continue
			}
			if pb.Status != "POSTED" || !allowedSeverity(pb.Severity) || pb.Severity != c.Severity {
				continue
			}
			if !allowedSeverity(c.Severity) {
				continue
			}
			if !windowOK(c.EventUTC, c.Region, wins) {
				continue
			}
			if !numericTS(pb.StartUTC) || !numericTS(pb.EndUTC) || c.EventUTC < pb.EndUTC {
				continue
			}
			candidates = append(candidates, i)
		}

		// Tie-break: latest end_utc first; on tie, earliest input row
		sort.SliceStable(candidates, func(i, j int) bool {
			a, b := playbacks[candidates[i]], playbacks[candidates[j]]
			if a.EndUTC == b.EndUTC {
				return a.Row < b.Row
			}
			return a.EndUTC > b.EndUTC
		})

		minutes, _ := strconv.Atoi(c.Minutes)
		if len(candidates) > 0 {
			idx := candidates[0]
			playbacks[idx].Used = true
			matchedCount++
			matchedMinutes += minutes
			writer.Write([]string{c.CreditID, c.StreamID, c.AccountID, playbacks[idx].Severity, c.Minutes, c.Reason, "MATCHED"})
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
