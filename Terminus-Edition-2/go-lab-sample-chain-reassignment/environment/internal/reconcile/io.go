package reconcile

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func readMaps(path string) ([]map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("%s has no header", path)
	}
	header := rows[0]
	out := make([]map[string]string, 0, len(rows)-1)
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, key := range header {
			val := ""
			if i < len(row) {
				val = row[i]
			}
			m[strings.TrimSpace(key)] = strings.TrimSpace(val)
		}
		out = append(out, m)
	}
	return out, nil
}

func loadAccessions(base string) ([]Accession, error) {
	rows, err := readMaps(filepath.Join(base, "data", "accessions.csv"))
	if err != nil {
		return nil, err
	}
	out := make([]Accession, 0, len(rows))
	for i, m := range rows {
		out = append(out, Accession{SampleID: m["sample_id"], PatientID: m["patient_id"], ChainID: m["chain_id"], Kind: m["kind"], Amount: m["amount"], SourceTS: m["source_ts"], Status: m["status"], Location: m["location"], Index: i})
	}
	return out, nil
}

func loadReassignments(base string) ([]Reassignment, error) {
	rows, err := readMaps(filepath.Join(base, "data", "reassignments.csv"))
	if err != nil {
		return nil, err
	}
	out := make([]Reassignment, 0, len(rows))
	for _, m := range rows {
		out = append(out, Reassignment{ActionID: m["action_id"], SampleID: m["sample_id"], PatientID: m["patient_id"], ChainID: m["chain_id"], Kind: m["kind"], Amount: m["amount"], ActionTS: m["action_ts"], Reason: m["reason"], Location: m["location"]})
	}
	return out, nil
}

func writeReport(base string, rows []OutputRow, summary Summary) error {
	if err := os.MkdirAll(filepath.Join(base, "out"), 0o755); err != nil {
		return err
	}
	report, err := os.Create(filepath.Join(base, "out", "reassignment_report.csv"))
	if err != nil {
		return err
	}
	w := csv.NewWriter(report)
	_ = w.Write([]string{"action_id", "sample_id", "patient_id", "chain_id", "kind", "amount", "reason", "matched_source_ts", "status"})
	for _, row := range rows {
		_ = w.Write([]string{row.ActionID, row.SampleID, row.PatientID, row.ChainID, row.Kind, row.Amount, row.Reason, row.MatchedSourceTS, row.Status})
	}
	w.Flush()
	if err := report.Close(); err != nil {
		return err
	}
	if err := w.Error(); err != nil {
		return err
	}

	body := fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n", summary.MatchedCount, summary.MatchedAmount, summary.UnmatchedCount, summary.UnmatchedAmount)
	return os.WriteFile(filepath.Join(base, "out", "reassignment_summary.txt"), []byte(body), 0o644)
}
