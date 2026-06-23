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
	manager := &Manager{cfg: cfg, roots: roots}
	if err := manager.reloadClientCertificate(); err != nil {
		return nil, err
	}
	return manager, nil
}

func (m *Manager) ClientTLSConfig() *tls.Config {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.clientTLS == nil {
		m.clientTLS = &tls.Config{MinVersion: tls.VersionTLS12}
		if m.cfg.ClientCertFile != "" && m.cfg.ClientKeyFile != "" {
			m.clientTLS.GetClientCertificate = func(*tls.CertificateRequestInfo) (*tls.Certificate, error) {
				m.mu.RLock()
				defer m.mu.RUnlock()
				if m.clientCert == nil {
					return &tls.Certificate{}, nil
				}
				copy := *m.clientCert
				return &copy, nil
			}
		}
	}
	m.clientTLS.RootCAs = m.roots
	m.clientTLS.ServerName = m.cfg.ServerName
	return m.clientTLS
}

func (m *Manager) Reload() error {
	if err := m.reloadTrustAnchors(); err != nil {
		return err
	}
	return m.reloadClientCertificate()
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
cat > /app/internal/upstream/client.go <<'GO'
package upstream

import (
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"time"

	"edge-gateway-tls-recovery/internal/tlsmaterial"
)

type Client struct {
	httpClient *http.Client
	transport  *http.Transport
}

func NewClient(material *tlsmaterial.Manager) *Client {
	transport := &http.Transport{
		TLSClientConfig: material.ClientTLSConfig(),
	}
	return &Client{
		httpClient: &http.Client{Transport: transport, Timeout: 5 * time.Second},
		transport:  transport,
	}
}

func NewClientWithTLSConfig(cfg *tls.Config) *Client {
	transport := &http.Transport{TLSClientConfig: cfg}
	return &Client{
		httpClient: &http.Client{Transport: transport, Timeout: 5 * time.Second},
		transport:  transport,
	}
}

func (c *Client) Get(ctx context.Context, target string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("upstream status %d: %s", resp.StatusCode, string(body))
	}
	return body, nil
}

func (c *Client) CloseIdleConnections() {
	c.transport.CloseIdleConnections()
}
GO
/usr/local/go/bin/gofmt -w /app/internal/tlsmaterial/manager.go /app/internal/upstream/client.go
