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
}

func NewManager(cfg Config) (*Manager, error) {
	roots, err := loadTrustAnchors(cfg.RootCAFile)
	if err != nil {
		return nil, err
	}
	manager := &Manager{cfg: cfg, roots: roots}
	if err := manager.reloadClientCertificate(); err != nil {
		return nil, err
	}
	return manager, nil
}

func (m *Manager) ClientTLSConfig() *tls.Config {
	cfg := &tls.Config{
		MinVersion: tls.VersionTLS12,
		RootCAs:    m.roots,
		ServerName: m.cfg.ServerName,
	}
	if m.cfg.ClientCertFile != "" && m.cfg.ClientKeyFile != "" {
		cfg.GetClientCertificate = func(*tls.CertificateRequestInfo) (*tls.Certificate, error) {
			m.mu.RLock()
			defer m.mu.RUnlock()
			if m.clientCert == nil {
				return &tls.Certificate{}, nil
			}
			copy := *m.clientCert
			return &copy, nil
		}
	}
	return cfg
}

func (m *Manager) Reload() error {
	return m.reloadClientCertificate()
}

func (m *Manager) reloadClientCertificate() error {
	if m.cfg.ClientCertFile == "" && m.cfg.ClientKeyFile == "" {
		return nil
	}
	if m.cfg.ClientCertFile == "" || m.cfg.ClientKeyFile == "" {
		return errors.New("client certificate and key must be configured together")
	}
	pair, err := tls.LoadX509KeyPair(m.cfg.ClientCertFile, m.cfg.ClientKeyFile)
	if err != nil {
		return err
	}
	m.mu.Lock()
	m.clientCert = &pair
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
