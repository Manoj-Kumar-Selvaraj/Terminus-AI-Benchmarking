package finbulk

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"finbulk/internal/db2sim"
)

type Detail struct {
	Seq     int
	Account string
	Op      string
	Amount  int
	GroupID string
	EventID string
}

type Header struct {
	BatchID      string
	BusinessDate string
	Source       string
}

type Trailer struct {
	BatchID string
	Count   int
	Total   int
}

type Summary map[string]any

type Options struct {
	StrictValidate    bool
	FailClosed        bool
	SkipApplied       bool
	RejectNotFound    bool
	RejectBusiness    bool
	LockAsPending     bool
	AtomicLimitUpdate bool
	ControlManifest   bool
	RejectReason      string
}

type Args struct {
	Batch               string
	Input               string
	DB                  string
	Out                 string
	Control             string
	AbendAfter          int
	AbendAfterLimMaster bool
	CloseDate           string
}

func ParseFile(path string) (Header, []Detail, Trailer, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Header{}, nil, Trailer{}, err
	}
	lines := make([]string, 0)
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimRight(line, "\r")
		if strings.TrimSpace(line) != "" {
			lines = append(lines, line)
		}
	}
	if len(lines) < 2 || !strings.HasPrefix(lines[0], "H") || !strings.HasPrefix(lines[len(lines)-1], "T") {
		return Header{}, nil, Trailer{}, fmt.Errorf("missing header or trailer")
	}
	h := Header{
		BatchID:      strings.TrimSpace(lines[0][1:11]),
		BusinessDate: lines[0][11:19],
		Source:       strings.TrimSpace(lines[0][19:27]),
	}
	tr := Trailer{
		BatchID: strings.TrimSpace(lines[len(lines)-1][1:11]),
		Count:   mustAtoi(lines[len(lines)-1][11:17]),
		Total:   signedAmount(lines[len(lines)-1][17:18], lines[len(lines)-1][18:30]),
	}
	details := make([]Detail, 0, len(lines)-2)
	for _, line := range lines[1 : len(lines)-1] {
		if len(line) < 49 || !strings.HasPrefix(line, "D") {
			continue
		}
		details = append(details, Detail{
			Seq:     mustAtoi(line[1:7]),
			Account: strings.TrimSpace(line[7:19]),
			Op:      strings.TrimSpace(line[19:22]),
			Amount:  signedAmount(line[22:23], line[23:35]),
			GroupID: strings.TrimSpace(line[35:41]),
			EventID: strings.TrimSpace(line[41:49]),
		})
	}
	return h, details, tr, nil
}

func mustAtoi(s string) int {
	v, _ := strconv.Atoi(strings.TrimSpace(s))
	return v
}

func signedAmount(sign, amount string) int {
	v, _ := strconv.Atoi(strings.TrimSpace(amount))
	if sign == "-" {
		return -v
	}
	return v
}

func WriteOutputs(outDir, batchID string, summary Summary, db db2sim.DB) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	sumPath := filepath.Join(outDir, fmt.Sprintf("summary_%s.json", batchID))
	b, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(sumPath, append(b, '\n'), 0o644); err != nil {
		return err
	}
	rejectPath := filepath.Join(outDir, fmt.Sprintf("rejects_%s.dat", batchID))
	return os.WriteFile(rejectPath, nil, 0o644)
}

func Run(args Args, opt Options) int {
	h, details, _, err := ParseFile(args.Input)
	batchID := args.Batch
	if batchID == "" {
		batchID = h.BatchID
	}
	if batchID == "" {
		batchID = "UNKNOWN"
	}
	db, loadErr := db2sim.Load(args.DB)
	if err != nil || loadErr != nil {
		if db == nil {
			db = db2sim.DB{}
		}
		_ = WriteOutputs(args.Out, batchID, Summary{
			"batch_id": batchID, "status": "ABEND", "applied": 0, "rejected": 0, "skipped": 0,
		}, db)
		return 12
	}
	summary := Summary{
		"batch_id": batchID, "status": "OK", "applied": 0, "rejected": 0, "skipped": 0,
	}
	for _, d := range details {
		code := applyDetail(db, batchID, d)
		if code != db2sim.OK {
			summary["status"] = "ABEND"
			summary["last_sqlcode"] = code
			_ = db2sim.Save(args.DB, db)
			_ = WriteOutputs(args.Out, batchID, summary, db)
			return 12
		}
		summary["applied"] = int(summary["applied"].(int)) + 1
		if args.AbendAfter > 0 && summary["applied"].(int) >= args.AbendAfter {
			summary["status"] = "SIMULATED_ABEND"
			_ = db2sim.Save(args.DB, db)
			_ = WriteOutputs(args.Out, batchID, summary, db)
			return 66
		}
	}
	_ = db2sim.Save(args.DB, db)
	_ = WriteOutputs(args.Out, batchID, summary, db)
	return 0
}

func applyDetail(db db2sim.DB, batchID string, d Detail) int {
	var code int
	switch d.Op {
	case "BAL":
		code = db2sim.UpdateBalance(db, d.Account, d.Amount)
		if code == db2sim.OK {
			db2sim.AppendLedger(db, batchID, d.Seq, d.Account, d.Amount, d.EventID)
		}
	case "RAT":
		code = db2sim.UpdateRate(db, d.Account, d.Amount)
	case "HLD":
		code = db2sim.UpdateHold(db, d.Account, d.Amount)
	case "LIM":
		code = db2sim.UpdateMasterLimit(db, d.Account, d.Amount)
		if code == db2sim.OK {
			code = db2sim.UpdateRiskLimit(db, d.Account, d.Amount)
		}
	default:
		code = db2sim.Constraint
	}
	if code == db2sim.OK {
		db2sim.AppendAudit(db, batchID, d.Seq, d.Account, d.Op, code, d.EventID)
		db2sim.MarkApplied(db, batchID, d.Seq, d.EventID, d.Account, d.Op)
	}
	return code
}
