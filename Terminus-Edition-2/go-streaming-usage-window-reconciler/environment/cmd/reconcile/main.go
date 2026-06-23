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
	StreamID, AccountID, Device, Minutes, StartUTC, EndUTC, Status, Region string
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
				m[key] = strings.TrimSpace(row[i])
			}
		}
		out = append(out, m)
	}
	return out, nil
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

	playbacks := []playback{}
	for _, row := range playbackRows {
		playbacks = append(playbacks, playback{
			StreamID: row["stream_id"], AccountID: row["account_id"], Device: row["device"],
			Minutes: row["minutes"], StartUTC: row["start_utc"], EndUTC: row["end_utc"],
			Status: row["status"], Region: row["region"],
		})
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
		streamID := row["stream_id"]
		minutes := row["minutes"]
		matchDevice := ""
		for _, pb := range playbacks {
			if strings.HasPrefix(pb.StreamID, streamID) || strings.HasPrefix(streamID, pb.StreamID) {
				if pb.Minutes == minutes {
					matchDevice = pb.Device
					break
				}
			}
		}
		min, _ := strconv.Atoi(minutes)
		if matchDevice != "" {
			matchedCount++
			matchedMinutes += min
			writer.Write([]string{row["credit_id"], streamID, row["account_id"], matchDevice, minutes, row["reason"], "MATCHED"})
		} else {
			unmatchedCount++
			unmatchedMinutes += min
			writer.Write([]string{row["credit_id"], streamID, row["account_id"], "", minutes, row["reason"], "UNMATCHED"})
		}
	}

	summary := fmt.Sprintf("matched_count=%d\nmatched_minutes=%d\nunmatched_count=%d\nunmatched_minutes=%d\n", matchedCount, matchedMinutes, unmatchedCount, unmatchedMinutes)
	if err := os.WriteFile(filepath.Clean("/app/out/usage_credit_summary.txt"), []byte(summary), 0644); err != nil {
		panic(err)
	}
}
