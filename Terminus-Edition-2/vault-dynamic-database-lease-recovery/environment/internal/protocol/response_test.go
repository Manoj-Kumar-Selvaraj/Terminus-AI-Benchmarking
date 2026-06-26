package protocol

import (
	"reflect"
	"testing"

	"vault-dynamic-database-lease-recovery/internal/model"
)

func sampleLease() model.Lease {
	return model.Lease{LeaseID: "lease-1", RequestID: "request-1", Username: "user-1", PasswordReference: "vaultref://opaque", IssuedAt: "2026-06-23T10:00:00Z", ExpiresAt: "2026-06-23T10:05:00Z", MaxExpiresAt: "2026-06-23T10:30:00Z", Renewable: true, Generation: 2, OwnerPodUID: "pod-1"}
}

func TestLeaseResponseVersion1Compatibility(t *testing.T) {
	got, err := LeaseResponse(sampleLease(), 1)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"expires_at", "lease_id", "password_reference", "renewable", "username"}
	keys := make([]string, 0, len(got))
	for k := range got {
		keys = append(keys, k)
	}
	// Map order is irrelevant; compare membership through a second map.
	m := map[string]bool{}
	for _, k := range keys {
		m[k] = true
	}
	for _, k := range want {
		if !m[k] {
			t.Fatalf("missing v1 key %s", k)
		}
	}
	if len(got) != len(want) {
		t.Fatalf("unexpected v1 fields: %#v", got)
	}
}

func TestLeaseResponseVersion2Compatibility(t *testing.T) {
	got, err := LeaseResponse(sampleLease(), 2)
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]any{"lease_id": "lease-1", "request_id": "request-1", "username": "user-1", "password_reference": "vaultref://opaque", "issued_at": "2026-06-23T10:00:00Z", "expires_at": "2026-06-23T10:05:00Z", "max_expires_at": "2026-06-23T10:30:00Z", "renewable": true, "generation": 2, "owner_pod_uid": "pod-1"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("v2 response mismatch: %#v", got)
	}
}

func TestLeaseResponseRejectsUnknownVersion(t *testing.T) {
	if _, err := LeaseResponse(sampleLease(), 7); err == nil {
		t.Fatal("expected unsupported protocol error")
	}
}
