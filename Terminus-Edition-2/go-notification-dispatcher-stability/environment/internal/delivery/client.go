package delivery

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"time"

	"notification-dispatcher/internal/dispatch"
	"notification-dispatcher/internal/idempotency"
)

type Client struct {
	HTTPClient *http.Client
	Ledger     *idempotency.Ledger
	MaxRetries int
}

func NewClient(httpClient *http.Client, ledger *idempotency.Ledger) *Client {
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	if ledger == nil {
		ledger = idempotency.NewLedger()
	}
	return &Client{HTTPClient: httpClient, Ledger: ledger, MaxRetries: 2}
}

func (c *Client) Deliver(ctx context.Context, job dispatch.Job) error {
	return c.deliverOnce(ctx, job, false)
}

func (c *Client) DeliverWithRetry(ctx context.Context, job dispatch.Job) error {
	var lastErr error
	for attempt := 0; attempt <= c.MaxRetries; attempt++ {
		err := c.deliverOnce(ctx, job, attempt > 0)
		if err == nil {
			return nil
		}
		lastErr = err
	}
	return lastErr
}

func (c *Client) deliverOnce(ctx context.Context, job dispatch.Job, retry bool) error {
	var body []byte
	var err error
	if IsLegacyClient(job.ClientID) && !retry {
		body, err = BuildLegacyPayload(job.EventType, job.Payload)
	} else {
		body, err = BuildModernPayload(job.EventType, job.Payload)
	}
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, job.TargetURL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode >= 500 {
		return fmt.Errorf("upstream status %d", resp.StatusCode)
	}
	if resp.StatusCode >= 400 {
		return fmt.Errorf("delivery rejected with status %d", resp.StatusCode)
	}
	return nil
}

func (c *Client) SetTimeout(d time.Duration) {
	c.HTTPClient.Timeout = d
}
