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
