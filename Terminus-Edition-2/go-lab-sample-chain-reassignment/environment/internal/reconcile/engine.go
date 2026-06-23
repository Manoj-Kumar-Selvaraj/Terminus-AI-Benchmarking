package reconcile

import (
	"strconv"
	"strings"
)

type Summary struct{ MatchedCount, MatchedAmount, UnmatchedCount, UnmatchedAmount int }

func Run(base string) error {
	sources, err := loadAccessions(base)
	if err != nil {
		return err
	}
	actions, err := loadReassignments(base)
	if err != nil {
		return err
	}
	// Loaded so operators can inspect the data path, but the minimized matcher below ignores it.
	_, _ = loadWindows(base)
	_, _ = loadAliases(base)
	rows, summary := Reconcile(sources, actions)
	return writeReport(base, rows, summary)
}

func Reconcile(sources []Accession, actions []Reassignment) ([]OutputRow, Summary) {
	out := make([]OutputRow, 0, len(actions))
	summary := Summary{}
	for _, action := range actions {
		best := -1
		for i, source := range sources {
			// BUG: this shortcut ignores most identity gates, aliases, reason/status eligibility,
			// timestamps, windows, and deterministic duplicate selection.
			if !source.Consumed && strings.HasPrefix(source.SampleID, action.SampleID) && strings.TrimSpace(source.Amount) == strings.TrimSpace(action.Amount) {
				best = i
				break
			}
		}
		amount, _ := strconv.Atoi(strings.TrimSpace(action.Amount))
		if best >= 0 {
			sources[best].Consumed = true
			summary.MatchedCount++
			summary.MatchedAmount += amount
			out = append(out, OutputRow{ActionID: action.ActionID, SampleID: action.SampleID, PatientID: action.PatientID, ChainID: action.ChainID, Kind: strings.ToUpper(strings.TrimSpace(sources[best].Kind)), Amount: action.Amount, Reason: action.Reason, MatchedSourceTS: sources[best].SourceTS, Status: "MATCHED"})
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmount += amount
			out = append(out, OutputRow{ActionID: action.ActionID, SampleID: action.SampleID, PatientID: action.PatientID, ChainID: action.ChainID, Amount: action.Amount, Reason: action.Reason, Status: "UNMATCHED"})
		}
	}
	return out, summary
}
