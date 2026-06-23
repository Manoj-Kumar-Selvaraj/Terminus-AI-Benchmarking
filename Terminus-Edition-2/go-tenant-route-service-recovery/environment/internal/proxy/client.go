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
	return &Client{HTTPClient: httpClient, Timeout: 100 * time.Millisecond}
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
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return Result{}, err
	}
	if resp.StatusCode >= 500 {
		return Result{}, fmt.Errorf("upstream status %d", resp.StatusCode)
	}
	_ = resp.Body.Close()
	return Result{StatusCode: resp.StatusCode, Body: string(data)}, nil
}

func IsTimeout(err error) bool {
	return errors.Is(err, context.DeadlineExceeded)
}
