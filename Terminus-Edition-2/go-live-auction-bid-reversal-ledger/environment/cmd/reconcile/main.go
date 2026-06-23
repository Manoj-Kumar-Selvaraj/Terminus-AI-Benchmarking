package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type bid struct {
	BidID, BidderID, SessionID, Channel, AmountCents, EventTS, Status, LotID string
}

type reversal struct {
	ReversalID, BidID, BidderID, SessionID, Channel, AmountCents, EventTS, Reason, LotID string
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
	out := make([]map[string]string, 0, len(rows)-1)
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, name := range header {
			if i < len(row) {
				m[name] = strings.TrimSpace(row[i])
			}
		}
		out = append(out, m)
	}
	return out, nil
}

func main() {
	bidRows, err := readCSV("/app/data/bids.csv")
	if err != nil {
		panic(err)
	}
	reversalRows, err := readCSV("/app/data/reversals.csv")
	if err != nil {
		panic(err)
	}

	bids := make([]bid, 0, len(bidRows))
	for _, row := range bidRows {
		bids = append(bids, bid{
			BidID:       row["bid_id"],
			BidderID:    row["bidder_id"],
			SessionID:   row["session_id"],
			Channel:     row["channel"],
			AmountCents: row["amount_cents"],
			EventTS:      row["event_ts"],
			Status:       row["status"],
			LotID:        row["lot_id"],
		})
	}

	os.MkdirAll("/app/out", 0755)
	reportPath := "/app/out/reversal_report.csv"
	report, err := os.Create(reportPath)
	if err != nil {
		panic(err)
	}
	defer report.Close()
	w := csv.NewWriter(report)
	defer w.Flush()
	w.Write([]string{"reversal_id", "bid_id", "bidder_id", "session_id", "channel", "amount_cents", "reason", "status"})

	matchedCount, unmatchedCount := 0, 0
	matchedAmount, unmatchedAmount := 0, 0
	for _, row := range reversalRows {
		rev := reversal{
			ReversalID:  row["reversal_id"],
			BidID:       row["bid_id"],
			BidderID:    row["bidder_id"],
			SessionID:   row["session_id"],
			Channel:     row["channel"],
			AmountCents: row["amount_cents"],
			EventTS:      row["event_ts"],
			Reason:      row["reason"],
			LotID:       row["lot_id"],
		}
		matched := ""
		for _, b := range bids {
			if strings.HasPrefix(b.BidID, rev.BidID) || strings.HasPrefix(rev.BidID, b.BidID) {
				if b.AmountCents == rev.AmountCents {
					matched = b.Channel
					break
				}
			}
		}
		amt, _ := strconv.Atoi(rev.AmountCents)
		if matched != "" {
			matchedCount++
			matchedAmount += amt
			w.Write([]string{rev.ReversalID, rev.BidID, rev.BidderID, rev.SessionID, matched, rev.AmountCents, rev.Reason, "MATCHED"})
		} else {
			unmatchedCount++
			unmatchedAmount += amt
			w.Write([]string{rev.ReversalID, rev.BidID, rev.BidderID, rev.SessionID, "", rev.AmountCents, rev.Reason, "UNMATCHED"})
		}
	}

	summary := fmt.Sprintf("matched_count=%d\nmatched_amount_cents=%d\nunmatched_count=%d\nunmatched_amount_cents=%d\n", matchedCount, matchedAmount, unmatchedCount, unmatchedAmount)
	if err := os.WriteFile(filepath.Clean("/app/out/reversal_summary.txt"), []byte(summary), 0644); err != nil {
		panic(err)
	}
}
