package tlsmaterial

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
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
	return &Manager{cfg: cfg, roots: x509.NewCertPool()}, nil
}

func (m *Manager) ClientTLSConfig() *tls.Config {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return &tls.Config{
		MinVersion: tls.VersionTLS12,
		RootCAs:    m.roots,
	}
}

func (m *Manager) Reload() error {
	return nil
}

func loadTrustAnchors(path string) (*x509.CertPool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	block, _ := pem.Decode(data)
	if block == nil || block.Type != "CERTIFICATE" {
		return nil, errors.New("trust file contains no certificate")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	pool.AddCert(cert)
	return pool, nil
}
