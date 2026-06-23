import subprocess
from pathlib import Path


APP = Path("/app")
PROXY_TEST = APP / "internal" / "proxy" / "client_recovery_test.go"


def write_proxy_tests():
    PROXY_TEST.write_text(
        r'''
package proxy

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
)

type verifierCloseTracker struct {
	closed *atomic.Bool
	body   *strings.Reader
}

func (c *verifierCloseTracker) Read(p []byte) (int, error) {
	return c.body.Read(p)
}

func (c *verifierCloseTracker) Close() error {
	c.closed.Store(true)
	return nil
}

type verifierRoundTripFunc func(*http.Request) (*http.Response, error)

func (f verifierRoundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func TestFetchClosesResponseBodyOnSuccessAndGatewayErrors(t *testing.T) {
	for _, status := range []int{http.StatusOK, http.StatusServiceUnavailable} {
		closed := &atomic.Bool{}
		client := NewClient(&http.Client{Transport: verifierRoundTripFunc(func(req *http.Request) (*http.Response, error) {
			return &http.Response{
				StatusCode: status,
				Body:       &verifierCloseTracker{closed: closed, body: strings.NewReader("payload")},
				Header:     make(http.Header),
				Request:    req,
			}, nil
		})})
		res, err := client.Fetch(context.Background(), "http://upstream.local/test")
		if status == http.StatusOK {
			if err != nil {
				t.Fatalf("unexpected error for status %d: %v", status, err)
			}
			if res.Body != "payload" {
				t.Fatalf("status %d body = %q, want payload", status, res.Body)
			}
		} else if status >= 500 {
			if err == nil {
				t.Fatalf("expected gateway error for status %d, got result %+v", status, res)
			}
		}
		if !closed.Load() {
			t.Fatalf("response body was not closed for status %d", status)
		}
	}
}

func TestFetchClosesResponseBodyWhenReadFails(t *testing.T) {
	closed := &atomic.Bool{}
	client := NewClient(&http.Client{Transport: verifierRoundTripFunc(func(req *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Body: readCloser{
				Reader: errReader{},
				close: func() error {
					closed.Store(true)
					return nil
				},
			},
			Header:  make(http.Header),
			Request: req,
		}, nil
	})})
	_, err := client.Fetch(context.Background(), "http://upstream.local/test")
	if err == nil {
		t.Fatalf("expected read error")
	}
	if !closed.Load() {
		t.Fatalf("response body was not closed after read failure")
	}
}

type errReader struct{}

func (errReader) Read([]byte) (int, error) {
	return 0, errors.New("read failed")
}

type readCloser struct {
	io.Reader
	close func() error
}

func (r readCloser) Close() error {
	return r.close()
}
'''
    )


def test_upstream_bodies_are_closed_for_repeated_failures():
    """Proxy fetches must close upstream bodies on success, gateway errors, and read errors."""
    write_proxy_tests()
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "./internal/proxy", "-run", "TestFetchCloses", "-count=1"],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout
