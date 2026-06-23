import subprocess
from pathlib import Path


APP = Path("/app")
ROUTES_TEST = APP / "internal" / "routes" / "stale_refresh_recovery_test.go"
SERVER_TEST = APP / "internal" / "server" / "stale_refresh_header_test.go"


def write_route_tests():
    ROUTES_TEST.write_text(
        r'''
package routes

import (
	"fmt"
	"sync"
	"testing"
)

func TestStaleAndEqualRevisionRefreshesDoNotRollBackRoutes(t *testing.T) {
	store := NewStore([]Route{{Tenant: "tenant-a", Upstream: "http://old", Revision: 1}})
	store.Refresh(Snapshot{Revision: 3, Routes: []Route{
		{Tenant: "tenant-a", Upstream: "http://new", Revision: 999},
		{Tenant: "tenant-b", Upstream: "http://b", Revision: 999},
	}})
	store.Refresh(Snapshot{Revision: 2, Routes: []Route{
		{Tenant: "tenant-a", Upstream: "http://stale", Revision: 2},
		{Tenant: "tenant-c", Upstream: "http://stale-c", Revision: 2},
	}})
	store.Refresh(Snapshot{Revision: 3, Routes: []Route{
		{Tenant: "tenant-a", Upstream: "http://equal", Revision: 3},
	}})

	if got := store.Revision(); got != 3 {
		t.Fatalf("revision = %d, want 3", got)
	}
	route, ok := store.Lookup("tenant-a")
	if !ok {
		t.Fatalf("tenant-a missing")
	}
	if route.Upstream != "http://new" || route.Revision != 3 {
		t.Fatalf("tenant-a route = %#v, want upstream http://new revision 3", route)
	}
	if _, ok := store.Lookup("tenant-b"); !ok {
		t.Fatalf("tenant-b from latest accepted snapshot was removed by stale replay")
	}
	if _, ok := store.Lookup("tenant-c"); ok {
		t.Fatalf("tenant-c from stale snapshot became routable")
	}
}

func TestMixedConcurrentRefreshesKeepHighestAcceptedSnapshot(t *testing.T) {
	store := NewStore([]Route{{Tenant: "tenant-base", Upstream: "http://base", Revision: 1}})
	var wg sync.WaitGroup
	start := make(chan struct{})

	for revision := 2; revision <= 20; revision++ {
		revision := revision
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			store.Refresh(Snapshot{Revision: revision, Routes: []Route{{
				Tenant: fmt.Sprintf("tenant-%02d", revision), Upstream: fmt.Sprintf("http://upstream-%02d", revision), Revision: -1,
			}}})
		}()
	}
	for revision := 1; revision <= 12; revision++ {
		revision := revision
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			store.Refresh(Snapshot{Revision: revision, Routes: []Route{{
				Tenant: "tenant-stale", Upstream: "http://stale", Revision: revision,
			}}})
		}()
	}
	for reader := 0; reader < 8; reader++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			for i := 0; i < 500; i++ {
				_, _ = store.Lookup("tenant-20")
				_ = store.Revision()
			}
		}()
	}

	close(start)
	wg.Wait()

	if got := store.Revision(); got != 20 {
		t.Fatalf("revision = %d, want 20", got)
	}
	route, ok := store.Lookup("tenant-20")
	if !ok || route.Upstream != "http://upstream-20" || route.Revision != 20 {
		t.Fatalf("tenant-20 route = %#v, ok=%v", route, ok)
	}
	if _, ok := store.Lookup("tenant-stale"); ok {
		t.Fatalf("stale tenant became routable after mixed refreshes")
	}
}
'''
    )


def write_server_tests():
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

func TestRouteHeaderUsesLatestAcceptedRevisionAfterStaleReplay(t *testing.T) {
	oldUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "old")
	}))
	defer oldUpstream.Close()
	newUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "new")
	}))
	defer newUpstream.Close()
	staleUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "stale")
	}))
	defer staleUpstream.Close()

	store := routes.NewStore([]routes.Route{{Tenant: "tenant-a", Upstream: oldUpstream.URL, Revision: 1}})
	store.Refresh(routes.Snapshot{Revision: 4, Routes: []routes.Route{{Tenant: "tenant-a", Upstream: newUpstream.URL, Revision: 99}}})
	store.Refresh(routes.Snapshot{Revision: 3, Routes: []routes.Route{{Tenant: "tenant-a", Upstream: staleUpstream.URL, Revision: 3}}})
	svc := New(store, proxy.NewClient(newUpstream.Client()))
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
	if got := resp.Header.Get("X-Route-Revision"); got != "4" {
		t.Fatalf("X-Route-Revision = %q, want 4", got)
	}
}
'''
    )


def test_stale_route_refreshes_are_ignored_without_rollback():
    """Stale route snapshots must be ignored atomically while newer snapshots remain accepted."""
    write_route_tests()
    write_server_tests()
    result = subprocess.run(
        [
            "/usr/local/go/bin/go",
            "test",
            "-race",
            "./internal/routes",
            "./internal/server",
            "-run",
            "Test(Stale|Mixed|RouteHeader)",
            "-count=1",
        ],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout
