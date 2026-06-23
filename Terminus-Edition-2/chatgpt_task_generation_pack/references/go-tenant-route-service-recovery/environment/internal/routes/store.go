package routes

import "errors"

type Store struct {
	revision int
	routes   map[string]Route
}

func NewStore(initial []Route) *Store {
	s := &Store{routes: map[string]Route{}}
	s.Refresh(Snapshot{Revision: 1, Routes: initial})
	return s
}

func (s *Store) Refresh(snapshot Snapshot) {
	s.revision = snapshot.Revision
	for _, route := range snapshot.Routes {
		s.routes[route.Tenant] = route
	}
	for tenant := range s.routes {
		seen := false
		for _, route := range snapshot.Routes {
			if route.Tenant == tenant {
				seen = true
				break
			}
		}
		if !seen {
			delete(s.routes, tenant)
		}
	}
}

func (s *Store) Lookup(tenant string) (Route, bool) {
	route, ok := s.routes[tenant]
	return route, ok
}

func (s *Store) Revision() int {
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
