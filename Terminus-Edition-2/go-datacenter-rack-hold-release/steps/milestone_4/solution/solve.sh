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

type source struct {
	id, asset, aisle, tier, amount, ts, status, rack string
	used                                             bool
}
type release struct{ id, hold, asset, aisle, tier, amount, ts, reason, rack string }
type window struct{ aisle, open, close, state string }
type audit struct{ total, matched, unmatched, matchedAmount, unmatchedAmount int }

func readCSV(path string) []map[string]string {
	f, err := os.Open(path)
	if err != nil {
		panic(err)
	}
	defer f.Close()
	r := csv.NewReader(f)
	rows, err := r.ReadAll()
	if err != nil {
		panic(err)
	}
	if len(rows) == 0 {
		return nil
	}
	headers := rows[0]
	out := []map[string]string{}
	for _, row := range rows[1:] {
		m := map[string]string{}
		for i, h := range headers {
			if i < len(row) {
				m[strings.TrimSpace(h)] = strings.TrimSpace(row[i])
			}
		}
		out = append(out, m)
	}
	return out
}

func digits14(s string) bool {
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

func validAmount(s string) (int, bool) {
	s = strings.TrimSpace(s)
	if s == "" || s == "0" || (len(s) > 1 && s[0] == '0') {
		return 0, false
	}
	for _, r := range s {
		if r < '0' || r > '9' {
			return 0, false
		}
	}
	n, err := strconv.Atoi(s)
	return n, err == nil && n > 0 && n <= 999999999
}

func loadAliases() map[string]string {
	aliases := map[string]string{"HOT": "HOT", "WARM": "WARM", "COLD": "COLD"}
	for _, row := range readCSV("/app/config/access_tier_aliases.csv") {
		a := strings.ToUpper(strings.TrimSpace(row["alias"]))
		c := strings.ToUpper(strings.TrimSpace(row["canonical"]))
		if a != "" && (c == "HOT" || c == "WARM" || c == "COLD") && a != c {
			aliases[a] = c
		}
	}
	return aliases
}

func canon(s string, aliases map[string]string) string {
	v := strings.ToUpper(strings.TrimSpace(s))
	if c, ok := aliases[v]; ok {
		return c
	}
	return v
}

func reasonOK(s string) bool { return s == "DECOMM" || s == "MIGRATE" || s == "OVERRIDE" }

func windowOK(src source, rel release, windows []window) bool {
	if !digits14(src.ts) || !digits14(rel.ts) {
		return false
	}
	for _, w := range windows {
		if w.aisle == src.aisle && strings.EqualFold(w.state, "OPEN") && digits14(w.open) && digits14(w.close) && src.ts >= w.open && src.ts <= w.close && rel.ts >= src.ts && rel.ts <= w.close {
			return true
		}
	}
	return false
}

func main() {
	aliases := loadAliases()
	sources := []source{}
	for _, m := range readCSV("/app/data/holds.csv") {
		sources = append(sources, source{m["hold_id"], m["asset_id"], m["aisle_id"], canon(m["access_tier"], aliases), strings.TrimSpace(m["amount"]), m["hold_ts"], m["status"], m["rack"], false})
	}
	releases := []release{}
	for _, m := range readCSV("/app/data/releases.csv") {
		releases = append(releases, release{m["release_id"], m["hold_id"], m["asset_id"], m["aisle_id"], canon(m["access_tier"], aliases), strings.TrimSpace(m["amount"]), m["release_ts"], m["reason"], m["rack"]})
	}
	windows := []window{}
	for _, m := range readCSV("/app/config/windows.csv") {
		windows = append(windows, window{m["aisle_id"], m["open_ts"], m["close_ts"], m["state"]})
	}

	os.MkdirAll("/app/out", 0755)
	report, _ := os.Create("/app/out/rack_release_report.csv")
	defer report.Close()
	rw := csv.NewWriter(report)
	defer rw.Flush()
	rw.Write([]string{"release_id", "hold_id", "asset_id", "aisle_id", "access_tier", "amount", "reason", "status"})
	rejFile, _ := os.Create("/app/out/rack_release_rejections.csv")
	defer rejFile.Close()
	rejw := csv.NewWriter(rejFile)
	defer rejw.Flush()
	rejw.Write([]string{"release_id", "code"})

	audits := map[string]*audit{}
	mc, uc, ma, ua := 0, 0, 0, 0
	for _, rel := range releases {
		if audits[rel.aisle] == nil {
			audits[rel.aisle] = &audit{}
		}
		audits[rel.aisle].total++
		relAmt, relAmtOK := validAmount(rel.amount)
		best := -1
		identity, nonWindowEligible := false, false
		for i, src := range sources {
			_, srcAmtOK := validAmount(src.amount)
			idMatch := src.id == rel.hold && src.asset == rel.asset && src.aisle == rel.aisle && src.rack == rel.rack && src.amount == rel.amount && relAmtOK && srcAmtOK
			if idMatch {
				identity = true
			}
			baseOK := idMatch && !src.used && src.status == "LOCKED" && src.tier == rel.tier && (src.tier == "HOT" || src.tier == "WARM" || src.tier == "COLD") && reasonOK(rel.reason) && digits14(src.ts) && digits14(rel.ts) && rel.ts >= src.ts
			if baseOK {
				nonWindowEligible = true
			}
			if baseOK && windowOK(src, rel, windows) {
				if best < 0 || src.ts > sources[best].ts || (src.ts == sources[best].ts && i < best) {
					best = i
				}
			}
		}
		if best >= 0 {
			sources[best].used = true
			mc++
			ma += relAmt
			audits[rel.aisle].matched++
			audits[rel.aisle].matchedAmount += relAmt
			rw.Write([]string{rel.id, rel.hold, rel.asset, rel.aisle, sources[best].tier, rel.amount, rel.reason, "MATCHED"})
			continue
		}
		uc++
		audits[rel.aisle].unmatched++
		if relAmtOK {
			ua += relAmt
			audits[rel.aisle].unmatchedAmount += relAmt
		}
		rw.Write([]string{rel.id, rel.hold, rel.asset, rel.aisle, "", rel.amount, rel.reason, "UNMATCHED"})
		code := "NO_ELIGIBLE_SOURCE"
		if !relAmtOK {
			code = "BAD_RELEASE_AMOUNT"
		} else if !digits14(rel.ts) {
			code = "BAD_RELEASE_TS"
		} else if !reasonOK(rel.reason) {
			code = "BAD_REASON"
		} else if !identity {
			code = "NO_SOURCE_IDENTITY"
		} else if nonWindowEligible {
			code = "WINDOW_INELIGIBLE"
		}
		rejw.Write([]string{rel.id, code})
	}
	os.WriteFile(filepath.Clean("/app/out/rack_release_summary.txt"), []byte(fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n", mc, ma, uc, ua)), 0644)

	auditFile, _ := os.Create("/app/out/rack_release_audit.csv")
	defer auditFile.Close()
	aw := csv.NewWriter(auditFile)
	defer aw.Flush()
	aw.Write([]string{"aisle_id", "total_releases", "matched_count", "unmatched_count", "matched_amount", "unmatched_amount"})
	aisles := []string{}
	for aisle := range audits {
		aisles = append(aisles, aisle)
	}
	sort.Strings(aisles)
	for _, aisle := range aisles {
		a := audits[aisle]
		aw.Write([]string{aisle, strconv.Itoa(a.total), strconv.Itoa(a.matched), strconv.Itoa(a.unmatched), strconv.Itoa(a.matchedAmount), strconv.Itoa(a.unmatchedAmount)})
	}
}
GO
/app/scripts/run_batch.sh
