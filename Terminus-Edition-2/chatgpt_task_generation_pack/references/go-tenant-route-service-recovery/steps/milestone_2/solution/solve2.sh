#!/usr/bin/env bash
set -euo pipefail
cat > /app/internal/routes/store.go <<'GO'
package routes

import (
	"errors"
	"sync"
)

type Store struct {
	mu       sync.RWMutex
	revision int
	routes   map[string]Route
}

func NewStore(initial []Route) *Store {
	s := &Store{routes: map[string]Route{}}
	s.Refresh(Snapshot{Revision: 1, Routes: initial})
	return s
}

func (s *Store) Refresh(snapshot Snapshot) {
	next := make(map[string]Route, len(snapshot.Routes))
	for _, route := range snapshot.Routes {
		route.Revision = snapshot.Revision
		next[route.Tenant] = route
	}
	s.mu.Lock()
	s.revision = snapshot.Revision
	s.routes = next
	s.mu.Unlock()
}

func (s *Store) Lookup(tenant string) (Route, bool) {
	s.mu.RLock()
	route, ok := s.routes[tenant]
	s.mu.RUnlock()
	return route, ok
}

func (s *Store) Revision() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.revision
}

func LoadSnapshot(revision int, upstreams map[string]string) (Snapshot, error) {
	if len(upstreams) == 0 {
		return Snapshot{}, errors.New("empty route snapshot")
	}
	out := Snapshot{Revision: revision}
	for tenant, upstream := range upstreams {
		out.Routes = append(out.Routes, Route{Tenant: tenant, Upstream: upstream, Revision: revision})
	}
	return out, nil
}
GO
cat > /app/internal/proxy/client.go <<'GO'
package proxy

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Client struct {
	HTTPClient *http.Client
	Timeout    time.Duration
}

type Result struct {
	StatusCode int
	Body       string
}

func NewClient(httpClient *http.Client) *Client {
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	return &Client{HTTPClient: httpClient}
}

func (c *Client) Fetch(ctx context.Context, upstream string) (Result, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, upstream, nil)
	if err != nil {
		return Result{}, err
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return Result{}, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return Result{}, err
	}
	if resp.StatusCode >= 500 {
		return Result{}, fmt.Errorf("upstream status %d", resp.StatusCode)
	}
	return Result{StatusCode: resp.StatusCode, Body: string(data)}, nil
}

func IsTimeout(err error) bool {
	return errors.Is(err, context.DeadlineExceeded)
}
GO
