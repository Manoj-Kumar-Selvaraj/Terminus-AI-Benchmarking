package reconcile

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

var amountRE = regexp.MustCompile(`^[0-9]+$`)

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

type csvTable struct {
	headers map[string]int
	rows    [][]string
}

type booking struct {
	row      int
	id       string
	team     string
	amount   int
	amountOK bool
	status   string
	tier     string
	tierOK   bool
}

type refund struct {
	row       int
	id        string
	team      string
	amount    int
	amountOK  bool
	amountRaw string
	tier      string
	tierOK    bool
}

type matchResult struct {
	idx  int
	tier string
}

func Run() error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	bookingsTable, err := readCSV("/app/data/bookings.csv")
	if err != nil {
		return err
	}
	refundsTable, err := readCSV("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	aliases := loadAliases("/app/config/room_aliases.csv")
	bookings := parseBookings(bookingsTable, aliases)
	refunds := parseRefunds(refundsTable, aliases)

	reportPath := filepath.Join("/app/out", "booking_refund_report.csv")
	report, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer report.Close()
	writer := csv.NewWriter(report)
	if err := writer.Write([]string{"booking_id", "team_id", "room_tier", "amount_cents", "status"}); err != nil {
		return err
	}

	used := make([]bool, len(bookings))
	summary := Summary{}
	for _, r := range refunds {
		chosen := findCandidate(r, bookings, used)
		status := "UNMATCHED"
		outTier := ""
		if chosen != nil {
			used[chosen.idx] = true
			status = "MATCHED"
			outTier = chosen.tier
			summary.MatchedCount++
			summary.MatchedAmountCents += r.amount
		} else {
			summary.UnmatchedCount++
			if r.amountOK {
				summary.UnmatchedAmountCents += r.amount
			}
		}
		if err := writer.Write([]string{r.id, r.team, outTier, r.amountRaw, status}); err != nil {
			return err
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		return err
	}
	body, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/booking_refund_summary.json", append(body, '\n'), 0o644)
}

func readCSV(path string) (csvTable, error) {
	f, err := os.Open(path)
	if err != nil {
		return csvTable{}, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	records, err := reader.ReadAll()
	if err != nil {
		return csvTable{}, err
	}
	table := csvTable{headers: map[string]int{}, rows: [][]string{}}
	if len(records) == 0 {
		return table, nil
	}
	for i, h := range records[0] {
		key := strings.ToLower(strings.TrimSpace(h))
		if key != "" {
			table.headers[key] = i
		}
	}
	table.rows = records[1:]
	return table, nil
}

func field(t csvTable, row []string, name string) string {
	idx, ok := t.headers[strings.ToLower(name)]
	if !ok || idx < 0 || idx >= len(row) {
		return ""
	}
	return strings.TrimSpace(row[idx])
}

func cleanUpper(s string) string { return strings.ToUpper(strings.TrimSpace(s)) }

func parseAmount(s string) (int, bool, string) {
	raw := strings.TrimSpace(s)
	if raw == "" || !amountRE.MatchString(raw) {
		return 0, false, raw
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0, false, raw
	}
	return n, true, raw
}

func canonicalTier(s string, aliases map[string]string) (string, bool, bool) {
	v := cleanUpper(s)
	if v == "ANY" {
		return "ANY", false, false
	}
	if mapped, ok := aliases[v]; ok {
		return mapped, true, false
	}
	if supportedTier(v) {
		return v, true, false
	}
	return v, false, false
}

func supportedTier(tier string) bool {
	switch tier {
	case "EASY", "HARD", "VIP":
		return true
	default:
		return false
	}
}

func parseBookings(t csvTable, aliases map[string]string) []booking {
	out := make([]booking, 0, len(t.rows))
	for i, row := range t.rows {
		amount, amountOK, _ := parseAmount(field(t, row, "amount_cents"))
		tier, tierOK, any := canonicalTier(field(t, row, "room_tier"), aliases)
		if any || !tierOK {
			tierOK = false
		}
		out = append(out, booking{
			row: i, id: field(t, row, "booking_id"), team: field(t, row, "team_id"),
			amount: amount, amountOK: amountOK, status: cleanUpper(field(t, row, "status")),
			tier: tier, tierOK: tierOK,
		})
	}
	return out
}

func parseRefunds(t csvTable, aliases map[string]string) []refund {
	out := make([]refund, 0, len(t.rows))
	for i, row := range t.rows {
		amount, amountOK, raw := parseAmount(field(t, row, "amount_cents"))
		tier, tierOK, any := canonicalTier(field(t, row, "room_tier"), aliases)
		if any || !tierOK {
			tierOK = false
		}
		out = append(out, refund{
			row: i, id: field(t, row, "booking_id"), team: field(t, row, "team_id"),
			amount: amount, amountOK: amountOK, amountRaw: raw, tier: tier, tierOK: tierOK,
		})
	}
	return out
}

func loadAliases(path string) map[string]string {
	aliases := map[string]string{"EASY": "EASY", "HARD": "HARD", "VIP": "VIP"}
	table, err := readCSV(path)
	if err != nil {
		return aliases
	}
	for _, row := range table.rows {
		alias := cleanUpper(field(table, row, "alias"))
		canonical := cleanUpper(field(table, row, "canonical"))
		enabled, enabledOK := parseBool(field(table, row, "enabled"))
		if alias == "" || canonical == "" || !supportedTier(canonical) || !enabledOK || !enabled {
			continue
		}
		if _, exists := aliases[alias]; !exists {
			aliases[alias] = canonical
		}
	}
	return aliases
}

func parseBool(v string) (bool, bool) {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "true", "t", "yes", "y", "1":
		return true, true
	case "false", "f", "no", "n", "0":
		return false, true
	default:
		return false, false
	}
}

func findCandidate(r refund, bookings []booking, used []bool) *matchResult {
	if r.id == "" || r.team == "" || !r.amountOK || !r.tierOK {
		return nil
	}
	for i, b := range bookings {
		if used[i] || !b.amountOK || !b.tierOK || b.id == "" || b.team == "" {
			continue
		}
		if b.id != r.id || b.team != r.team || b.amount != r.amount || b.status != "COMPLETED" {
			continue
		}
		if b.tier != r.tier {
			continue
		}
		return &matchResult{idx: i, tier: b.tier}
	}
	return nil
}
