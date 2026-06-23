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
	StreamID, AccountID, Device, Minutes, StartUTC, EndUTC, Status, Region string
	Row int
	Used bool
}

type credit struct {
	CreditID, StreamID, AccountID, Device, Minutes, EventUTC, Reason, Region string
}

type cutoff struct {
	Region, CutoffUTC, State string
}

func readCSV(path string) ([]map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	rows, err := reader.ReadAll()
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
		for i, key := range header {
			if i < len(row) {
				m[strings.TrimSpace(key)] = strings.TrimSpace(row[i])
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

func canonicalDevice(s string) string {
	switch strings.ToUpper(strings.TrimSpace(s)) {
	case "TV", "CTV":
		return "CTV"
	case "PHONE", "MOBILE":
		return "MOBILE"
	case "WEBAPP", "BROWSER":
		return "BROWSER"
	default:
		return strings.ToUpper(strings.TrimSpace(s))
	}
}

func allowedDevice(s string) bool {
	return s == "CTV" || s == "MOBILE" || s == "BROWSER"
}

func eligibleReason(s string) bool {
	return s == "BUFFER" || s == "DUPLICATE" || s == "OUTAGE"
}

func cutoffOK(c credit, cutoffs []cutoff) bool {
	if !numericTS(c.EventUTC) {
		return false
	}
	for _, co := range cutoffs {
		if co.Region == c.Region && co.State == "OPEN" && numericTS(co.CutoffUTC) && c.EventUTC <= co.CutoffUTC {
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
	cutoffRows, err := readCSV("/app/config/region_cutoffs.csv")
	if err != nil {
		panic(err)
	}

	playbacks := []playback{}
	for i, row := range playbackRows {
		playbacks = append(playbacks, playback{StreamID: row["stream_id"], AccountID: row["account_id"], Device: canonicalDevice(row["device"]), Minutes: row["minutes"], StartUTC: row["start_utc"], EndUTC: row["end_utc"], Status: row["status"], Region: row["region"], Row: i})
	}
	cutoffs := []cutoff{}
	for _, row := range cutoffRows {
		cutoffs = append(cutoffs, cutoff{Region: row["region"], CutoffUTC: row["cutoff_utc"], State: row["state"]})
	}

	os.MkdirAll("/app/out", 0755)
	report, err := os.Create("/app/out/usage_credit_report.csv")
	if err != nil {
		panic(err)
	}
	defer report.Close()
	writer := csv.NewWriter(report)
	defer writer.Flush()
	writer.Write([]string{"credit_id", "stream_id", "account_id", "device", "minutes", "reason", "status"})

	matchedCount, unmatchedCount := 0, 0
	matchedMinutes, unmatchedMinutes := 0, 0
	for _, row := range creditRows {
		c := credit{CreditID: row["credit_id"], StreamID: row["stream_id"], AccountID: row["account_id"], Device: canonicalDevice(row["device"]), Minutes: row["minutes"], EventUTC: row["event_utc"], Reason: row["reason"], Region: row["region"]}
		candidates := []int{}
		for i, pb := range playbacks {
			if pb.Used || pb.StreamID != c.StreamID || pb.AccountID != c.AccountID || pb.Region != c.Region || pb.Minutes != c.Minutes {
				continue
			}
			if pb.Status != "POSTED" || !allowedDevice(pb.Device) || pb.Device != c.Device || !eligibleReason(c.Reason) || !cutoffOK(c, cutoffs) {
				continue
			}
			if !numericTS(pb.StartUTC) || !numericTS(pb.EndUTC) || c.EventUTC < pb.EndUTC {
				continue
			}
			candidates = append(candidates, i)
		}
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
			writer.Write([]string{c.CreditID, c.StreamID, c.AccountID, playbacks[idx].Device, c.Minutes, c.Reason, "MATCHED"})
		} else {
			unmatchedCount++
			unmatchedMinutes += minutes
			writer.Write([]string{c.CreditID, c.StreamID, c.AccountID, "", c.Minutes, c.Reason, "UNMATCHED"})
		}
	}

	summary := fmt.Sprintf("matched_count=%d\nmatched_minutes=%d\nunmatched_count=%d\nunmatched_minutes=%d\n", matchedCount, matchedMinutes, unmatchedCount, unmatchedMinutes)
	if err := os.WriteFile(filepath.Clean("/app/out/usage_credit_summary.txt"), []byte(summary), 0644); err != nil {
		panic(err)
	}
}
GO
/app/scripts/run_batch.sh
