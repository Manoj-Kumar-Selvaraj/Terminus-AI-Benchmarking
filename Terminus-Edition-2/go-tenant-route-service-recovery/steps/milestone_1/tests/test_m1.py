import subprocess
from pathlib import Path


APP = Path("/app")
ROUTES_TEST = APP / "internal" / "routes" / "store_recovery_test.go"
SERVER_TEST = APP / "internal" / "server" / "revision_header_recovery_test.go"


def write_route_tests():
    ROUTES_TEST.write_text(
        r'''
package routes

import (
	"fmt"
	"sync"
	"testing"
)

func TestRefreshAndLookupRemainStableDuringOverlap(t *testing.T) {
	initial := []Route{{Tenant: "tenant-a", Upstream: "http://upstream-a", Revision: 1}}
	store := NewStore(initial)
	start := make(chan struct{})
	var wg sync.WaitGroup

	for reader := 0; reader < 8; reader++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for i := 0; i < 400; i++ {
				if route, ok := store.Lookup("tenant-a"); ok && route.Tenant != "tenant-a" {
					t.Fatalf("lookup returned route for wrong tenant: %#v", route)
				}
			}
		}()
	}

	for writer := 0; writer < 4; writer++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			<-start
			for i := 0; i < 120; i++ {
				snapshot := Snapshot{Revision: id*1000 + i}
				for tenant := 0; tenant < 40; tenant++ {
					name := fmt.Sprintf("tenant-%02d", tenant)
					snapshot.Routes = append(snapshot.Routes, Route{Tenant: name, Upstream: "http://upstream", Revision: snapshot.Revision})
				}
				snapshot.Routes = append(snapshot.Routes, Route{Tenant: "tenant-a", Upstream: "http://upstream-a", Revision: snapshot.Revision})
				store.Refresh(snapshot)
			}
		}(writer)
	}

	close(start)
	wg.Wait()
}

func TestRefreshReplacesMissingTenants(t *testing.T) {
	store := NewStore([]Route{
		{Tenant: "tenant-a", Upstream: "http://a", Revision: 1},
		{Tenant: "tenant-b", Upstream: "http://b", Revision: 1},
	})
	store.Refresh(Snapshot{Revision: 2, Routes: []Route{{Tenant: "tenant-a", Upstream: "http://a2", Revision: 2}}})
	if _, ok := store.Lookup("tenant-b"); ok {
		t.Fatalf("tenant absent from replacement snapshot remained routable")
	}
	if got := store.Revision(); got != 2 {
		t.Fatalf("revision = %d, want 2", got)
	}
}

func TestRefreshNormalizesRouteRevisionToSnapshot(t *testing.T) {
	store := NewStore([]Route{{Tenant: "tenant-a", Upstream: "http://a", Revision: 99}})
	store.Refresh(Snapshot{Revision: 2, Routes: []Route{{Tenant: "tenant-a", Upstream: "http://a2", Revision: 99}}})
	route, ok := store.Lookup("tenant-a")
	if !ok {
		t.Fatalf("tenant-a missing after refresh")
	}
	if route.Revision != 2 {
		t.Fatalf("route revision = %d, want snapshot revision 2", route.Revision)
	}
}
'''
    )


def write_server_header_tests():
    SERVER_TEST.write_text(
        r'''
package server

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"tenant-route-service/internal/proxy"
	"tenant-route-service/internal/routes"
)

func TestRouteResponseUsesNormalizedRevisionHeaderAfterRefresh(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "ok")
	}))
	defer upstream.Close()

	store := routes.NewStore([]routes.Route{{Tenant: "tenant-a", Upstream: upstream.URL, Revision: 99}})
	store.Refresh(routes.Snapshot{
		Revision: 2,
		Routes:   []routes.Route{{Tenant: "tenant-a", Upstream: upstream.URL, Revision: 99}},
	})
	svc := New(store, proxy.NewClient(upstream.Client()))
	router := httptest.NewServer(svc.Handler())
	defer router.Close()

	resp, err := router.Client().Get(router.URL + "/route/tenant-a")
	if err != nil {
		t.Fatalf("GET /route/tenant-a failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	if got := resp.Header.Get("X-Route-Revision"); got != "2" {
		t.Fatalf("X-Route-Revision = %q, want normalized revision 2", got)
	}
}
'''
    )


def test_route_refresh_overlap_is_race_free_and_replaces_snapshot():
    """Route refresh must be race-free, replace absent tenants, and normalize revisions."""
    write_route_tests()
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "-race", "./internal/routes", "-run", "TestRefresh", "-count=1"],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout


def test_route_response_uses_normalized_revision_header_after_refresh():
    """HTTP route responses must expose the normalized snapshot revision header."""
    write_server_header_tests()
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "./internal/server", "-run", "TestRouteResponseUsesNormalizedRevisionHeader", "-count=1"],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout
