import subprocess
from pathlib import Path


APP = Path("/app")
SERVER_TEST = APP / "internal" / "server" / "timeout_recovery_test.go"


def write_timeout_tests():
    SERVER_TEST.write_text(
        r'''
package server

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"tenant-route-service/internal/proxy"
	"tenant-route-service/internal/routes"
)

func TestStalledUpstreamReturnsGatewayTimeoutInsideContract(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(250 * time.Millisecond)
		fmt.Fprint(w, "late")
	}))
	defer upstream.Close()

	store := routes.NewStore([]routes.Route{{Tenant: "tenant-slow", Upstream: upstream.URL, Revision: 9}})
	svc := New(store, proxy.NewClient(upstream.Client()))
	svc.SLO = 60 * time.Millisecond
	router := httptest.NewServer(svc.Handler())
	defer router.Close()

	start := time.Now()
	resp, err := router.Client().Get(router.URL + "/route/tenant-slow")
	if err != nil {
		t.Fatalf("router request failed: %v", err)
	}
	defer resp.Body.Close()
	elapsed := time.Since(start)
	if resp.StatusCode != http.StatusGatewayTimeout {
		t.Fatalf("status = %d, want 504", resp.StatusCode)
	}
	if elapsed > 500*time.Millisecond {
		t.Fatalf("timeout response took %s, want inside service contract", elapsed)
	}
}

func TestDefaultSLOUsesLatencyContract(t *testing.T) {
	slowUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(120 * time.Millisecond)
		fmt.Fprint(w, "late")
	}))
	defer slowUpstream.Close()

	store := routes.NewStore([]routes.Route{{Tenant: "tenant-default", Upstream: slowUpstream.URL, Revision: 9}})
	svc := New(store, proxy.NewClient(slowUpstream.Client()))
	router := httptest.NewServer(svc.Handler())
	defer router.Close()

	start := time.Now()
	resp, err := router.Client().Get(router.URL + "/route/tenant-default")
	if err != nil {
		t.Fatalf("router request failed: %v", err)
	}
	defer resp.Body.Close()
	elapsed := time.Since(start)
	if resp.StatusCode != http.StatusGatewayTimeout {
		t.Fatalf("status = %d, want 504", resp.StatusCode)
	}
	if elapsed > 500*time.Millisecond {
		t.Fatalf("default SLO timeout took %s, want within contract window", elapsed)
	}
}

func TestDefaultSLOBracketsLatencyContract(t *testing.T) {
	fastUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(80 * time.Millisecond)
		fmt.Fprint(w, "inside-contract")
	}))
	defer fastUpstream.Close()

	fastStore := routes.NewStore([]routes.Route{{Tenant: "tenant-fast-default", Upstream: fastUpstream.URL, Revision: 11}})
	fastSvc := New(fastStore, proxy.NewClient(fastUpstream.Client()))
	fastRouter := httptest.NewServer(fastSvc.Handler())
	defer fastRouter.Close()

	fastResp, err := fastRouter.Client().Get(fastRouter.URL + "/route/tenant-fast-default")
	if err != nil {
		t.Fatalf("fast default-SLO request failed: %v", err)
	}
	defer fastResp.Body.Close()
	if fastResp.StatusCode != http.StatusOK {
		t.Fatalf("80ms upstream status = %d, want 200", fastResp.StatusCode)
	}

	slowUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(120 * time.Millisecond)
		fmt.Fprint(w, "outside-contract")
	}))
	defer slowUpstream.Close()

	slowStore := routes.NewStore([]routes.Route{{Tenant: "tenant-slow-default", Upstream: slowUpstream.URL, Revision: 12}})
	slowSvc := New(slowStore, proxy.NewClient(slowUpstream.Client()))
	slowRouter := httptest.NewServer(slowSvc.Handler())
	defer slowRouter.Close()

	start := time.Now()
	slowResp, err := slowRouter.Client().Get(slowRouter.URL + "/route/tenant-slow-default")
	if err != nil {
		t.Fatalf("slow default-SLO request failed: %v", err)
	}
	defer slowResp.Body.Close()
	elapsed := time.Since(start)
	if slowResp.StatusCode != http.StatusGatewayTimeout {
		t.Fatalf("120ms upstream status = %d, want 504", slowResp.StatusCode)
	}
	if elapsed > 500*time.Millisecond {
		t.Fatalf("120ms upstream timeout took %s, want within contract window", elapsed)
	}
}

func TestSuccessfulUpstreamStillPassesThrough(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusAccepted)
		fmt.Fprint(w, "accepted")
	}))
	defer upstream.Close()

	store := routes.NewStore([]routes.Route{{Tenant: "tenant-fast", Upstream: upstream.URL, Revision: 10}})
	svc := New(store, proxy.NewClient(upstream.Client()))
	svc.SLO = 100 * time.Millisecond
	router := httptest.NewServer(svc.Handler())
	defer router.Close()

	resp, err := router.Client().Get(router.URL + "/route/tenant-fast")
	if err != nil {
		t.Fatalf("router request failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusAccepted {
		t.Fatalf("status = %d, want 202", resp.StatusCode)
	}
	if got := resp.Header.Get("X-Route-Revision"); got != "1" {
		t.Fatalf("X-Route-Revision = %q, want 1", got)
	}
}
'''
    )


def test_stalled_upstream_obeys_latency_contract_without_breaking_success_path():
    """Stalled upstreams must time out on the 100ms contract while fast calls still pass through."""
    write_timeout_tests()
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "./internal/server", "-run", "Test(Stalled|Default|Successful)", "-count=1"],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout
