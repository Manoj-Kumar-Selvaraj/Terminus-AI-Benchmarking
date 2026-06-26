package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Client struct {
	HTTP *http.Client
}

func NewClient() *Client {
	return &Client{HTTP: &http.Client{Timeout: 10 * time.Second}}
}

func (c *Client) Apply(ctx context.Context, baseURL string, req ApplyRequest) (ApplyResponse, int, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return ApplyResponse{}, 0, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(baseURL, "/")+"/v1/policies/apply", bytes.NewReader(body))
	if err != nil {
		return ApplyResponse{}, 0, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(httpReq)
	if err != nil {
		return ApplyResponse{}, 0, err
	}
	defer resp.Body.Close()
	payload, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return ApplyResponse{}, resp.StatusCode, err
	}
	var out ApplyResponse
	if err := json.Unmarshal(payload, &out); err != nil {
		return ApplyResponse{}, resp.StatusCode, fmt.Errorf("decode gateway response: %w", err)
	}
	return out, resp.StatusCode, nil
}
