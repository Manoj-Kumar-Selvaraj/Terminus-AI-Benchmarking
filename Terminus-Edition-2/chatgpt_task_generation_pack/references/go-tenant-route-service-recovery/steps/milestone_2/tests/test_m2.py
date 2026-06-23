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

type closeTracker struct {
	closed *atomic.Bool
	body   *strings.Reader
}

func (c *closeTracker) Read(p []byte) (int, error) {
	return c.body.Read(p)
}

func (c *closeTracker) Close() error {
	c.closed.Store(true)
	return nil
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func TestFetchClosesResponseBodyOnSuccessAndGatewayErrors(t *testing.T) {
	for _, status := range []int{http.StatusOK, http.StatusServiceUnavailable} {
		closed := &atomic.Bool{}
		client := NewClient(&http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return &http.Response{
				StatusCode: status,
				Body:       &closeTracker{closed: closed, body: strings.NewReader("payload")},
				Header:     make(http.Header),
				Request:    req,
			}, nil
		})})
		_, _ = client.Fetch(context.Background(), "http://upstream.local/test")
		if !closed.Load() {
			t.Fatalf("response body was not closed for status %d", status)
		}
	}
}

func TestFetchClosesResponseBodyWhenReadFails(t *testing.T) {
	closed := &atomic.Bool{}
	client := NewClient(&http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
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
