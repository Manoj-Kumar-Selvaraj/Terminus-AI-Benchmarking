#!/usr/bin/env bash
set -euo pipefail
cat > /app/internal/tlsmaterial/manager.go <<'GO'
package tlsmaterial

import (
	"crypto/tls"
	"crypto/x509"
	"errors"
	"os"
	"sync"
)

type Config struct {
	RootCAFile     string
	ServerName     string
	ClientCertFile string
	ClientKeyFile  string
}

type Manager struct {
	cfg        Config
	mu         sync.RWMutex
	roots      *x509.CertPool
	clientCert *tls.Certificate
	clientTLS  *tls.Config
}

func NewManager(cfg Config) (*Manager, error) {
	roots, err := loadTrustAnchors(cfg.RootCAFile)
	if err != nil {
		return nil, err
	}
	return &Manager{cfg: cfg, roots: roots}, nil
}

func (m *Manager) ClientTLSConfig() *tls.Config {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.clientTLS == nil {
		m.clientTLS = &tls.Config{MinVersion: tls.VersionTLS12}
	}
	m.clientTLS.RootCAs = m.roots
	m.clientTLS.ServerName = m.cfg.ServerName
	return m.clientTLS
}

func (m *Manager) Reload() error {
	return m.reloadTrustAnchors()
}

func (m *Manager) reloadTrustAnchors() error {
	roots, err := loadTrustAnchors(m.cfg.RootCAFile)
	if err != nil {
		return err
	}
	m.mu.Lock()
	m.roots = roots
	if m.clientTLS != nil {
		m.clientTLS.RootCAs = roots
	}
	m.mu.Unlock()
	return nil
}

func loadTrustAnchors(path string) (*x509.CertPool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if ok := pool.AppendCertsFromPEM(data); !ok {
		return nil, errors.New("trust file contains no certificate")
	}
	return pool, nil
}
GO
/usr/local/go/bin/gofmt -w /app/internal/tlsmaterial/manager.go
