package state

import (
	"os"
	"path/filepath"
	"testing"

	"vault-dynamic-database-lease-recovery/internal/model"
)

func TestFingerprintBindsStableIssuanceIdentity(t *testing.T) {
	base := model.IssueRequest{RequestID: "r", PodUID: "p", VaultRole: "v", DatabaseRole: "d", RequestedAt: "first", Generation: 1}
	replay := base
	replay.RequestedAt = "later"
	replay.Generation = 9
	if Fingerprint(base) != Fingerprint(replay) {
		t.Fatal("retry metadata changed stable fingerprint")
	}
	conflict := base
	conflict.PodUID = "other"
	if Fingerprint(base) == Fingerprint(conflict) {
		t.Fatal("owner change did not change fingerprint")
	}
}

func TestLoadJournalRecoversOnlyTornTail(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("LEASE_AGENT_STATE_DIR", dir)
	s := New()
	path := filepath.Join(dir, "lease-journal.jsonl")
	if err := os.WriteFile(path, []byte("{\"event\":\"A\"}\n{\"event\":"), 0600); err != nil {
		t.Fatal(err)
	}
	events, err := s.LoadJournal(true)
	if err != nil {
		t.Fatal(err)
	}
	if len(events) != 1 {
		t.Fatalf("got %d committed events", len(events))
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != "{\"event\":\"A\"}\n" {
		t.Fatalf("unexpected repaired journal %q", raw)
	}
}
