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

func materialTLSConfig(material *tlsmaterial.Manager) *tls.Config {
	source := material.ClientTLSConfig()
	if source == nil {
		return &tls.Config{MinVersion: tls.VersionTLS12}
	}
	// Keep only the static verification fields; dynamic credential hooks are
	// re-established by the gateway supervisor after reload.
	return &tls.Config{
		MinVersion: source.MinVersion,
		RootCAs:    source.RootCAs,
		ServerName: source.ServerName,
	}
}

func NewClient(material *tlsmaterial.Manager) *Client {
	transport := &http.Transport{
		TLSClientConfig: materialTLSConfig(material),
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
