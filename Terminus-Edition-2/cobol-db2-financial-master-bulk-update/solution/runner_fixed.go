package finbulk

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"

	"finbulk/internal/db2sim"
)

const chainZeros = "0000000000000000000000000000000000000000000000000000000000000000"

type Detail struct {
	Seq      int
	Account  string
	Op       string
	Amount   int
	GroupID  string
	EventID  string
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
	StrictValidate     bool
	FailClosed         bool
	SkipApplied        bool
	RejectNotFound     bool
	RejectBusiness     bool
	LockAsPending      bool
	AtomicLimitUpdate  bool
	ControlManifest    bool
	RejectReason       string
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

func parseAmount(sign, amount string) (int, error) {
	if sign != "+" && sign != "-" {
		return 0, fmt.Errorf("bad signed amount")
	}
	if _, err := strconv.Atoi(amount); err != nil {
		return 0, fmt.Errorf("bad signed amount")
	}
	v, _ := strconv.Atoi(amount)
	if sign == "-" {
		return -v, nil
	}
	return v, nil
}

func ParseFile(path string) (Header, []Detail, Trailer, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Header{}, nil, Trailer{}, err
	}
	lines := make([]string, 0)
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimRight(line, "\r")
		if strings.TrimSpace(line) == "" {
			continue
		}
		lines = append(lines, line)
	}
	if len(lines) < 2 || !strings.HasPrefix(lines[0], "H") || !strings.HasPrefix(lines[len(lines)-1], "T") {
		return Header{}, nil, Trailer{}, fmt.Errorf("missing header or trailer")
	}
	h := Header{
		BatchID:      strings.TrimSpace(lines[0][1:11]),
		BusinessDate: lines[0][11:19],
		Source:       strings.TrimSpace(lines[0][19:27]),
	}
	tl := lines[len(lines)-1]
	total, err := parseAmount(tl[17:18], tl[18:30])
	if err != nil {
		return Header{}, nil, Trailer{}, err
	}
	tr := Trailer{
		BatchID: strings.TrimSpace(tl[1:11]),
		Count:   mustAtoi(tl[11:17]),
		Total:   total,
	}
	details := make([]Detail, 0, len(lines)-2)
	for _, line := range lines[1 : len(lines)-1] {
		if !strings.HasPrefix(line, "D") {
			return Header{}, nil, Trailer{}, fmt.Errorf("bad record type %s", line[:1])
		}
		amt, err := parseAmount(line[22:23], line[23:35])
		if err != nil {
			return Header{}, nil, Trailer{}, err
		}
		details = append(details, Detail{
			Seq:     mustAtoi(line[1:7]),
			Account: strings.TrimSpace(line[7:19]),
			Op:      strings.TrimSpace(line[19:22]),
			Amount:  amt,
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

func validateContract(h Header, details []Detail, tr Trailer, strict bool) error {
	if h.BatchID != tr.BatchID {
		return fmt.Errorf("header/trailer batch mismatch")
	}
	if len(details) != tr.Count {
		return fmt.Errorf("trailer count mismatch")
	}
	if !strict {
		return nil
	}
	total := 0
	for _, d := range details {
		if d.Seq <= 0 || d.Account == "" || !validOp(d.Op) {
			return fmt.Errorf("malformed detail record")
		}
		if d.Op == "BAL" {
			total += d.Amount
		}
	}
	if total != tr.Total {
		return fmt.Errorf("trailer financial total mismatch")
	}
	return nil
}

func validOp(op string) bool {
	switch op {
	case "BAL", "RAT", "HLD", "LIM":
		return true
	default:
		return false
	}
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
	var rejectLines []string
	if rejects, _ := db["rejects"].([]any); rejects != nil {
		for _, item := range rejects {
			r, _ := item.(map[string]any)
			if r == nil || r["batch_id"] != batchID {
				continue
			}
			seq := int(num(r["seq"]))
			acct, _ := r["account"].(string)
			sqlcode := int(num(r["sqlcode"]))
			reason, _ := r["reason"].(string)
			if len(reason) > 32 {
				reason = reason[:32]
			}
			rejectLines = append(rejectLines, fmt.Sprintf("R%06d%-12s%+05d%-32s", seq, acct, sqlcode, reason))
		}
	}
	rejectData := []byte(strings.Join(rejectLines, "\n"))
	if len(rejectLines) > 0 {
		rejectData = append(rejectData, '\n')
	}
	if err := os.WriteFile(rejectPath, rejectData, 0o644); err != nil {
		return err
	}
	locks := []any{}
	if pending, _ := db["pending_locks"].([]any); pending != nil {
		for _, item := range pending {
			r, _ := item.(map[string]any)
			if r != nil && r["batch_id"] == batchID {
				locks = append(locks, r)
			}
		}
	}
	lb, err := json.MarshalIndent(locks, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(outDir, fmt.Sprintf("pending_locks_%s.json", batchID)), append(lb, '\n'), 0o644)
}

func num(v any) float64 {
	switch t := v.(type) {
	case float64:
		return t
	case int:
		return float64(t)
	default:
		return 0
	}
}

func loadControl(path string, h Header, details []Detail, tr Trailer, inputPath string) (map[string]any, string, error) {
	sum := sha256.Sum256(mustRead(inputPath))
	hash := hex.EncodeToString(sum[:])
	if path == "" {
		return nil, hash, nil
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, hash, fmt.Errorf("malformed control manifest: %w", err)
	}
	var control map[string]any
	if err := json.Unmarshal(raw, &control); err != nil {
		return nil, hash, fmt.Errorf("malformed control manifest: %w", err)
	}
	expected := map[string]any{
		"batch_id": h.BatchID, "business_date": h.BusinessDate, "source": h.Source,
		"detail_count": len(details), "financial_total": tr.Total,
	}
	if control["batch_id"] != expected["batch_id"] {
		return nil, hash, fmt.Errorf("control batch id mismatch")
	}
	if control["business_date"] != expected["business_date"] {
		return nil, hash, fmt.Errorf("control business date mismatch")
	}
	if control["source"] != expected["source"] {
		return nil, hash, fmt.Errorf("control source mismatch")
	}
	if int(num(control["expected_detail_count"])) != len(details) {
		return nil, hash, fmt.Errorf("control detail count mismatch")
	}
	if int(num(control["expected_financial_total"])) != tr.Total {
		return nil, hash, fmt.Errorf("control financial total mismatch")
	}
	return control, hash, nil
}

func mustRead(path string) []byte {
	b, _ := os.ReadFile(path)
	return b
}

func enforceControlReplay(db db2sim.DB, batchID, inputHash string) error {
	totals, _ := db["control_totals"].(map[string]any)
	if totals == nil {
		return nil
	}
	entry, _ := totals[batchID].(map[string]any)
	if entry != nil && entry["input_sha256"] != inputHash {
		return fmt.Errorf("duplicate batch id with different input hash")
	}
	return nil
}

func chainTipForDate(db db2sim.DB, businessDate string) (priorChain, priorBatchID string) {
	priorChain = chainZeros
	chainIndex, _ := db["chain_index"].(map[string]any)
	if chainIndex == nil {
		return
	}
	arr, _ := chainIndex[businessDate].([]any)
	if len(arr) == 0 {
		return
	}
	tipID, _ := arr[len(arr)-1].(string)
	totals, _ := db["control_totals"].(map[string]any)
	if totals == nil {
		return
	}
	tip, _ := totals[tipID].(map[string]any)
	if tip == nil {
		return
	}
	if c, ok := tip["chain_sha256"].(string); ok {
		priorChain = c
	}
	priorBatchID = tipID
	return
}

func computeChainHash(prior, batchID, inputHash, businessDate string) string {
	h := sha256.Sum256([]byte(prior + batchID + inputHash + businessDate))
	return hex.EncodeToString(h[:])
}

func enforceDependency(db db2sim.DB, control map[string]any, businessDate string) error {
	if control == nil {
		return nil
	}
	raw, has := control["prior_batch_id"]
	if !has || raw == nil {
		return nil
	}
	expected, ok := raw.(string)
	if !ok {
		return fmt.Errorf("UNMET_DEPENDENCY: prior_batch_id must be string")
	}
	_, tip := chainTipForDate(db, businessDate)
	if expected != tip {
		return fmt.Errorf("UNMET_DEPENDENCY: prior_batch_id %q does not match chain tip %q for date %s", expected, tip, businessDate)
	}
	return nil
}

func acquireBatchLock(dbPath, batchID string) (*os.File, bool, error) {
	dir := filepath.Dir(dbPath)
	if dir == "" {
		dir = "."
	}
	lockPath := filepath.Join(dir, ".lock_"+batchID)
	f, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, false, err
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		if err == syscall.EWOULDBLOCK {
			return nil, true, nil
		}
		return nil, false, err
	}
	return f, false, nil
}

func releaseBatchLock(f *os.File) {
	if f == nil {
		return
	}
	_ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN)
	_ = f.Close()
}

func recordControlTotal(db db2sim.DB, batchID string, control map[string]any, inputHash string, summary Summary, businessDate string) {
	if control == nil {
		return
	}
	status := "UNKNOWN"
	if summary["status"] == "OK" && int(num(summary["pending_locks"])) == 0 {
		status = "SETTLED"
	} else if s, ok := summary["status"].(string); ok {
		status = s
	}
	totals, _ := db["control_totals"].(map[string]any)
	if totals == nil {
		totals = map[string]any{}
		db["control_totals"] = totals
	}
	// Idempotent rerun: existing settled entry with same input hash — preserve all chain fields.
	if existing, _ := totals[batchID].(map[string]any); existing != nil {
		if existing["input_sha256"] == inputHash && existing["status"] == "SETTLED" {
			// Do not mutate chain or chain_index.
			return
		}
	}
	priorChain, priorBatchID := chainTipForDate(db, businessDate)
	chainHex := computeChainHash(priorChain, batchID, inputHash, businessDate)
	var priorBatchValue any
	if priorBatchID != "" {
		priorBatchValue = priorBatchID
	}
	totals[batchID] = map[string]any{
		"batch_id":           batchID,
		"business_date":      control["business_date"],
		"source":             control["source"],
		"detail_count":       int(num(control["expected_detail_count"])),
		"financial_total":    int(num(control["expected_financial_total"])),
		"input_sha256":       inputHash,
		"status":             status,
		"prior_chain_sha256": priorChain,
		"chain_sha256":       chainHex,
		"prior_batch_id":     priorBatchValue,
	}
	if status != "SETTLED" {
		return
	}
	chainIndex, _ := db["chain_index"].(map[string]any)
	if chainIndex == nil {
		chainIndex = map[string]any{}
		db["chain_index"] = chainIndex
	}
	arr, _ := chainIndex[businessDate].([]any)
	chainIndex[businessDate] = append(arr, batchID)
}

func applyDetail(db db2sim.DB, batchID string, d Detail, opt Options, abendAfterLimMaster bool) (int, bool) {
	if opt.SkipApplied {
		if dup := db2sim.EnsureNotDuplicate(db, batchID, d.Seq); dup != db2sim.OK {
			return dup, false
		}
	}
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
		if opt.AtomicLimitUpdate {
			staged := db2sim.Clone(db)
			code = db2sim.UpdateMasterLimit(staged, d.Account, d.Amount)
			if code == db2sim.OK {
				if abendAfterLimMaster {
					// Mid-LIM abend: master half staged but never committed; risk untouched.
					return 0, true
				}
				code = db2sim.UpdateRiskLimit(staged, d.Account, d.Amount)
			}
			if code == db2sim.OK {
				db2sim.CommitSnapshot(db, staged)
			}
		} else {
			code = db2sim.UpdateMasterLimit(db, d.Account, d.Amount)
			if code == db2sim.OK {
				code = db2sim.UpdateRiskLimit(db, d.Account, d.Amount)
			}
		}
	default:
		code = db2sim.Constraint
	}
	if code == db2sim.OK {
		db2sim.AppendAudit(db, batchID, d.Seq, d.Account, d.Op, code, d.EventID)
		db2sim.MarkApplied(db, batchID, d.Seq, d.EventID, d.Account, d.Op)
	}
	return code, false
}

func failedSummary(batchID string, err error) Summary {
	return Summary{
		"batch_id": batchID, "status": "FAILED_CLOSED", "error": err.Error(),
		"applied": 0, "rejected": 0, "skipped": 0,
	}
}

func Run(args Args, opt Options) int {
	if args.CloseDate != "" {
		return runClose(args)
	}
	h, details, tr, err := ParseFile(args.Input)
	batchID := args.Batch
	if err == nil && batchID == "" {
		batchID = h.BatchID
	}
	if err != nil {
		batchID = fallbackBatch(args.Batch)
		if opt.FailClosed {
			db, _ := db2sim.Load(args.DB)
			_ = WriteOutputs(args.Out, batchID, failedSummary(batchID, err), db)
			return 2
		}
		return 12
	}
	if err := validateContract(h, details, tr, opt.StrictValidate); err != nil {
		if opt.FailClosed {
			db, _ := db2sim.Load(args.DB)
			_ = WriteOutputs(args.Out, batchID, failedSummary(batchID, err), db)
			return 2
		}
		return 12
	}
	var control map[string]any
	var inputHash string
	if opt.ControlManifest {
		var cerr error
		control, inputHash, cerr = loadControl(args.Control, h, details, tr, args.Input)
		if cerr != nil {
			if opt.FailClosed {
				db, _ := db2sim.Load(args.DB)
				_ = WriteOutputs(args.Out, batchID, failedSummary(batchID, cerr), db)
				return 2
			}
			return 12
		}
	}
	// Acquire per-batch fencing lock BEFORE loading DB so a concurrent run cannot race a half-applied state.
	lockFile, busy, lockErr := acquireBatchLock(args.DB, batchID)
	if lockErr != nil {
		busyDB := db2sim.DB{}
		_ = WriteOutputs(args.Out, batchID, failedSummary(batchID, lockErr), busyDB)
		return 12
	}
	if busy {
		busyDB := db2sim.DB{}
		summary := Summary{
			"batch_id": batchID, "status": "BATCH_BUSY",
			"applied": 0, "rejected": 0, "skipped": 0, "pending_locks": 0,
			"error": "another finbulk process holds the fencing lock for this batch",
		}
		_ = WriteOutputs(args.Out, batchID, summary, busyDB)
		return 73
	}
	defer releaseBatchLock(lockFile)

	db, err := db2sim.Load(args.DB)
	if err != nil {
		return 12
	}
	if opt.ControlManifest {
		if err := enforceControlReplay(db, batchID, inputHash); err != nil {
			if opt.FailClosed {
				_ = WriteOutputs(args.Out, batchID, failedSummary(batchID, err), db)
				return 2
			}
			return 12
		}
		// Cross-batch dependency: enforced before any mutation.
		if err := enforceDependency(db, control, h.BusinessDate); err != nil {
			if opt.FailClosed {
				_ = WriteOutputs(args.Out, batchID, failedSummary(batchID, err), db)
				return 2
			}
			return 12
		}
	}
	return runDetails(args, opt, db, batchID, details, control, inputHash, h.BusinessDate)
}

func fallbackBatch(batch string) string {
	if batch != "" {
		return batch
	}
	return "UNKNOWN"
}

func runDetails(args Args, opt Options, db db2sim.DB, batchID string, details []Detail, control map[string]any, inputHash string, businessDate string) int {
	summary := Summary{
		"batch_id": batchID, "applied": 0, "rejected": 0, "skipped": 0,
		"pending_locks": 0, "status": "OK",
	}
	for _, d := range details {
		if opt.SkipApplied && db2sim.IsApplied(db, batchID, d.Seq) {
			summary["skipped"] = int(num(summary["skipped"])) + 1
			continue
		}
		code, midLimAbend := applyDetail(db, batchID, d, opt, args.AbendAfterLimMaster)
		if midLimAbend {
			summary["status"] = "SIMULATED_ABEND"
			summary["error"] = "abend after master limit, before risk commit"
			_ = db2sim.Save(args.DB, db)
			_ = WriteOutputs(args.Out, batchID, summary, db)
			return 66
		}
		switch {
		case code == db2sim.OK:
			summary["applied"] = int(num(summary["applied"])) + 1
		case code == db2sim.Duplicate && opt.SkipApplied:
			summary["skipped"] = int(num(summary["skipped"])) + 1
		case code == db2sim.LockTimeout && opt.LockAsPending:
			holder := "UNKNOWN"
			if locks, _ := db["locks"].(map[string]any); locks != nil {
				if h, ok := locks[d.Account].(string); ok {
					holder = h
				}
			}
			db2sim.AppendPendingLock(db, batchID, d.Seq, d.Account, holder, d.EventID)
			summary["pending_locks"] = int(num(summary["pending_locks"])) + 1
			summary["status"] = "RETRYABLE_LOCK"
			_ = db2sim.Save(args.DB, db)
			_ = WriteOutputs(args.Out, batchID, summary, db)
			return 75
		case code == db2sim.NotFound && opt.RejectNotFound:
			db2sim.AppendReject(db, batchID, d.Seq, d.Account, code, "MASTER_ROW_NOT_FOUND", d.EventID)
			summary["rejected"] = int(num(summary["rejected"])) + 1
		case (code == db2sim.NotFound || code == db2sim.Constraint || code == db2sim.LockTimeout) && opt.RejectBusiness:
			reason := opt.RejectReason
			if reason == "" {
				reason = "BUSINESS_REJECT"
			}
			db2sim.AppendReject(db, batchID, d.Seq, d.Account, code, reason, d.EventID)
			summary["rejected"] = int(num(summary["rejected"])) + 1
		default:
			summary["status"] = "ABEND"
			summary["last_sqlcode"] = code
			_ = db2sim.Save(args.DB, db)
			_ = WriteOutputs(args.Out, batchID, summary, db)
			return 12
		}
		if args.AbendAfter > 0 && int(num(summary["applied"])) >= args.AbendAfter {
			summary["status"] = "SIMULATED_ABEND"
			_ = db2sim.Save(args.DB, db)
			_ = WriteOutputs(args.Out, batchID, summary, db)
			return 66
		}
	}
	if opt.ControlManifest {
		recordControlTotal(db, batchID, control, inputHash, summary, businessDate)
	}
	_ = db2sim.Save(args.DB, db)
	_ = WriteOutputs(args.Out, batchID, summary, db)
	return 0
}

// runClose performs the end-of-day close ceremony for the requested business date.
// It is strictly read-only: no DB mutation, no per-batch flock, no checkpoint write.
func runClose(args Args) int {
	if err := os.MkdirAll(args.Out, 0o755); err != nil {
		return 12
	}
	db, loadErr := db2sim.Load(args.DB)
	if loadErr != nil {
		writeCloseBroken(args.Out, args.CloseDate, "cannot load database: "+loadErr.Error())
		return 2
	}
	totals, _ := db["control_totals"].(map[string]any)
	chainIndex, _ := db["chain_index"].(map[string]any)
	var rawArr []any
	if chainIndex != nil {
		rawArr, _ = chainIndex[args.CloseDate].([]any)
	}
	entries := make([]closeBatchView, 0, len(rawArr))
	priorChain := chainZeros
	for _, raw := range rawArr {
		bid, _ := raw.(string)
		if bid == "" {
			writeCloseBroken(args.Out, args.CloseDate, "chain index contains empty batch id")
			return 2
		}
		var entry map[string]any
		if totals != nil {
			entry, _ = totals[bid].(map[string]any)
		}
		if entry == nil {
			writeCloseBroken(args.Out, args.CloseDate, fmt.Sprintf("chain index references unknown batch %s", bid))
			return 2
		}
		storedPrior, _ := entry["prior_chain_sha256"].(string)
		storedChain, _ := entry["chain_sha256"].(string)
		inputHash, _ := entry["input_sha256"].(string)
		status, _ := entry["status"].(string)
		bizDate, _ := entry["business_date"].(string)
		if status != "SETTLED" {
			writeCloseBroken(args.Out, args.CloseDate, fmt.Sprintf("batch %s is not SETTLED", bid))
			return 2
		}
		if bizDate != args.CloseDate {
			writeCloseBroken(args.Out, args.CloseDate, fmt.Sprintf("batch %s business_date %q does not match close date %q", bid, bizDate, args.CloseDate))
			return 2
		}
		if storedPrior != priorChain {
			writeCloseBroken(args.Out, args.CloseDate, fmt.Sprintf("chain break at batch %s: stored prior %s != expected %s", bid, storedPrior, priorChain))
			return 2
		}
		recomputed := computeChainHash(priorChain, bid, inputHash, bizDate)
		if recomputed != storedChain {
			writeCloseBroken(args.Out, args.CloseDate, fmt.Sprintf("chain hash mismatch at batch %s: stored %s != recomputed %s", bid, storedChain, recomputed))
			return 2
		}
		entries = append(entries, closeBatchView{
			BatchID:        bid,
			DetailCount:    int(num(entry["detail_count"])),
			FinancialTotal: int(num(entry["financial_total"])),
			ChainHex:       storedChain,
		})
		priorChain = storedChain
	}

	chainRoot := chainZeros
	if len(entries) > 0 {
		chainRoot = entries[len(entries)-1].ChainHex
	}
	grandTotal := 0
	batchesOut := make([]map[string]any, 0, len(entries))
	for _, e := range entries {
		grandTotal += e.FinancialTotal
		batchesOut = append(batchesOut, map[string]any{
			"batch_id":        e.BatchID,
			"detail_count":    e.DetailCount,
			"financial_total": e.FinancialTotal,
			"chain_sha256":    e.ChainHex,
		})
	}
	summary := map[string]any{
		"status":        "CLOSED",
		"close_date":    args.CloseDate,
		"batch_count":   len(entries),
		"chain_root":    chainRoot,
		"grand_total":   grandTotal,
		"batches":       batchesOut,
	}
	if err := writeCloseSummary(args.Out, args.CloseDate, summary); err != nil {
		return 12
	}
	if err := writeGLFeed(args.Out, args.CloseDate, entries, grandTotal); err != nil {
		return 12
	}
	return 0
}

func writeCloseSummary(outDir, date string, summary map[string]any) error {
	b, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(outDir, fmt.Sprintf("close_%s.json", date)), append(b, '\n'), 0o644)
}

func writeCloseBroken(outDir, date, reason string) {
	summary := map[string]any{
		"status":      "CLOSE_BROKEN",
		"close_date":  date,
		"batch_count": 0,
		"chain_root":  chainZeros,
		"grand_total": 0,
		"batches":     []map[string]any{},
		"error":       reason,
	}
	_ = writeCloseSummary(outDir, date, summary)
	// Empty zero-byte GL feed file per contract.
	_ = os.WriteFile(filepath.Join(outDir, fmt.Sprintf("glfeed_%s.dat", date)), []byte{}, 0o644)
}

type closeBatchView struct {
	BatchID        string
	DetailCount    int
	FinancialTotal int
	ChainHex       string
}

func writeGLFeed(outDir, date string, entries []closeBatchView, grandTotal int) error {
	path := filepath.Join(outDir, fmt.Sprintf("glfeed_%s.dat", date))
	if len(entries) == 0 {
		// Empty date — zero-byte file per contract.
		return os.WriteFile(path, []byte{}, 0o644)
	}
	var buf strings.Builder
	// Header: H date(8) count(6) = 15 bytes
	buf.WriteString(fmt.Sprintf("H%-8s%06d", date, len(entries)))
	buf.WriteByte('\n')
	for _, e := range entries {
		sign := "+"
		amt := e.FinancialTotal
		if amt < 0 {
			sign = "-"
			amt = -amt
		}
		// G batch(10) chain(64) count(6) sign(1) cents(12) = 94 bytes
		buf.WriteString(fmt.Sprintf("G%-10s%64s%06d%s%012d", e.BatchID, e.ChainHex, e.DetailCount, sign, amt))
		buf.WriteByte('\n')
	}
	sign := "+"
	g := grandTotal
	if g < 0 {
		sign = "-"
		g = -g
	}
	// T date(8) count(6) sign(1) cents(12) = 28 bytes
	buf.WriteString(fmt.Sprintf("T%-8s%06d%s%012d", date, len(entries), sign, g))
	buf.WriteByte('\n')
	return os.WriteFile(path, []byte(buf.String()), 0o644)
}
