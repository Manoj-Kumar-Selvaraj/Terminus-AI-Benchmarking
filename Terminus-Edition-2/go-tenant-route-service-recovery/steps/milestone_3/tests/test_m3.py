import subprocess
from pathlib import Path


APP = Path("/app")
SERVER_TEST = APP / "internal" / "server" / "shutdown_recovery_test.go"


def write_shutdown_tests():
    SERVER_TEST.write_text(
        r'''
package server

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"tenant-route-service/internal/proxy"
	"tenant-route-service/internal/routes"
)

func TestShutdownAllowsAcceptedRequestToFinish(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(60 * time.Millisecond)
		fmt.Fprint(w, "ok-after-drain")
	}))
	defer upstream.Close()

	store := routes.NewStore([]routes.Route{{Tenant: "tenant-a", Upstream: upstream.URL, Revision: 7}})
	svc := New(store, proxy.NewClient(upstream.Client()))
	srv := &http.Server{Handler: svc.Handler()}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() {
		_ = srv.Serve(ln)
	}()

	done := make(chan error, 1)
	go func() {
		resp, err := http.Get("http://" + ln.Addr().String() + "/route/tenant-a")
		if err != nil {
			done <- err
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			done <- fmt.Errorf("status = %d, want 200", resp.StatusCode)
			return
		}
		done <- nil
	}()

	time.Sleep(15 * time.Millisecond)
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	if err := svc.ShutdownWithServer(ctx, srv); err != nil {
		t.Fatalf("shutdown returned error: %v", err)
	}
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("accepted request did not finish cleanly: %v", err)
		}
	case <-time.After(350 * time.Millisecond):
		t.Fatalf("accepted request did not finish before grace window")
	}
}
'''
    )


def test_termination_keeps_accepted_request_inside_grace_window():
    """Graceful shutdown must let an already accepted route request finish cleanly."""
    write_shutdown_tests()
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "./internal/server", "-run", "TestShutdownAllows", "-count=1"],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout
