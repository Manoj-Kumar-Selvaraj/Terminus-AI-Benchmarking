package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"os"
	"path/filepath"
	"testing"
)

func TestIssuerScopedCollisionUsesDistinctSecrets(t *testing.T) {
	profile, err := findSecret("profile-ci", "rot-17")
	if err != nil {
		t.Fatal(err)
	}
	partner, err := findSecret("partner-ci", "rot-17")
	if err != nil {
		t.Fatal(err)
	}
	if profile == partner {
		t.Fatal("colliding kid resolved to one global secret")
	}
}

func TestSignatureMatchesHMACSHA256(t *testing.T) {
	input := "header.payload"
	secret := "synthetic-secret"
	got := sign(input, secret)
	h := hmac.New(sha256.New, []byte(secret))
	h.Write([]byte(input))
	if got != b64(h.Sum(nil)) {
		t.Fatalf("unexpected signature: %s", got)
	}
}

func TestCopyTreePreservesFixtureBytes(t *testing.T) {
	src := t.TempDir()
	dst := t.TempDir()
	if err := os.MkdirAll(filepath.Join(src, "nested"), 0755); err != nil {
		t.Fatal(err)
	}
	want := []byte("fixture\n")
	if err := os.WriteFile(filepath.Join(src, "nested", "a.txt"), want, 0644); err != nil {
		t.Fatal(err)
	}
	copyTree(src, filepath.Join(dst, "copy"))
	got, err := os.ReadFile(filepath.Join(dst, "copy", "nested", "a.txt"))
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(want) {
		t.Fatalf("copy mismatch: %q", got)
	}
}

func TestRawURLBase64HasNoPadding(t *testing.T) {
	got := b64([]byte{0xff, 0xee, 0xdd})
	if got == "" || got[len(got)-1] == '=' {
		t.Fatalf("not raw URL base64: %q", got)
	}
}
