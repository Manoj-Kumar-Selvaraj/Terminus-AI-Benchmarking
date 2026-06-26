#!/usr/bin/env bash
set -Eeuo pipefail
rm -f /app/internal/delivery/*_test.go
cat > /app/internal/dispatch/dispatcher.go <<'GO'
package dispatch

import (
    "context"
    "errors"
    "sync"
)

var ErrStopped = errors.New("dispatcher stopped")

type DeliverFunc func(ctx context.Context, job Job) error

type Dispatcher struct {
    mu           sync.Mutex
    jobs         chan Job
    ctx          context.Context
    cancel       context.CancelFunc
    wg           sync.WaitGroup
    shutdownOnce sync.Once
    shutdownDone chan struct{}
    workerCount  int
    queueDepth   int
    stopped      bool
    deliver      DeliverFunc
}

func NewDispatcher(workerCount int, deliver DeliverFunc) *Dispatcher {
    if workerCount < 1 {
        workerCount = 1
    }
    if deliver == nil {
        deliver = func(context.Context, Job) error { return nil }
    }
    ctx, cancel := context.WithCancel(context.Background())
    d := &Dispatcher{
        jobs: make(chan Job, workerCount*4),
        ctx: ctx,
        cancel: cancel,
        shutdownDone: make(chan struct{}),
        workerCount: workerCount,
        deliver: deliver,
    }
    for i := 0; i < workerCount; i++ {
        d.wg.Add(1)
        go d.worker()
    }
    return d
}

func (d *Dispatcher) Enqueue(job Job) error {
    if job.OperationKey == "" {
        return errors.New("operation key required")
    }
    d.mu.Lock()
    if d.stopped {
        d.mu.Unlock()
        return ErrStopped
    }
    d.queueDepth++
    d.mu.Unlock()

    select {
    case d.jobs <- job:
        return nil
    case <-d.ctx.Done():
        d.mu.Lock()
        if d.queueDepth > 0 {
            d.queueDepth--
        }
        d.mu.Unlock()
        return ErrStopped
    }
}

func (d *Dispatcher) QueueDepth() int {
    d.mu.Lock()
    defer d.mu.Unlock()
    return d.queueDepth
}

func (d *Dispatcher) Shutdown(ctx context.Context) error {
    d.shutdownOnce.Do(func() {
        d.mu.Lock()
        d.stopped = true
        d.mu.Unlock()
        d.cancel()
        go func() {
            d.wg.Wait()
            d.mu.Lock()
            d.queueDepth = 0
            d.mu.Unlock()
            close(d.shutdownDone)
        }()
    })

    select {
    case <-d.shutdownDone:
        return nil
    case <-ctx.Done():
        return ctx.Err()
    }
}

func (d *Dispatcher) Context() context.Context { return d.ctx }
GO
cat > /app/internal/dispatch/worker.go <<'GO'
package dispatch

func (d *Dispatcher) worker() {
    defer d.wg.Done()
    for {
        select {
        case <-d.ctx.Done():
            return
        default:
        }
        select {
        case <-d.ctx.Done():
            return
        case job := <-d.jobs:
            d.markDequeued()
            _ = d.deliver(d.ctx, job)
        }
    }
}

func (d *Dispatcher) markDequeued() {
    d.mu.Lock()
    if d.queueDepth > 0 {
        d.queueDepth--
    }
    d.mu.Unlock()
}
GO
cat > /app/internal/idempotency/ledger.go <<'GO'
package idempotency

import (
    "context"
    "sync"
)

type call struct {
    done chan struct{}
    err  error
}

type Ledger struct {
    mu        sync.Mutex
    delivered map[string]struct{}
    inFlight  map[string]*call
}

func NewLedger() *Ledger {
    return &Ledger{
        delivered: map[string]struct{}{},
        inFlight: map[string]*call{},
    }
}

func (l *Ledger) Seen(key string) bool {
    l.mu.Lock()
    defer l.mu.Unlock()
    _, ok := l.delivered[key]
    return ok
}

func (l *Ledger) Record(key string) {
    l.mu.Lock()
    defer l.mu.Unlock()
    l.delivered[key] = struct{}{}
}

func (l *Ledger) Do(ctx context.Context, key string, fn func() error) error {
    l.mu.Lock()
    if _, ok := l.delivered[key]; ok {
        l.mu.Unlock()
        return nil
    }
    if existing, ok := l.inFlight[key]; ok {
        l.mu.Unlock()
        select {
        case <-existing.done:
            return existing.err
        case <-ctx.Done():
            return ctx.Err()
        }
    }
    current := &call{done: make(chan struct{})}
    l.inFlight[key] = current
    l.mu.Unlock()

    err := fn()

    l.mu.Lock()
    current.err = err
    if err == nil {
        l.delivered[key] = struct{}{}
    }
    delete(l.inFlight, key)
    close(current.done)
    l.mu.Unlock()
    return err
}
GO
cat > /app/internal/delivery/client.go <<'GO'
package delivery

import (
    "bytes"
    "context"
    "errors"
    "fmt"
    "io"
    "net/http"
    "time"

    "notification-dispatcher/internal/dispatch"
    "notification-dispatcher/internal/idempotency"
)

type statusError struct { status int }
func (e *statusError) Error() string { return fmt.Sprintf("upstream status %d", e.status) }

type Client struct {
    HTTPClient *http.Client
    Ledger     *idempotency.Ledger
    MaxRetries int
}

func NewClient(httpClient *http.Client, ledger *idempotency.Ledger) *Client {
    if httpClient == nil { httpClient = http.DefaultClient }
    if ledger == nil { ledger = idempotency.NewLedger() }
    return &Client{HTTPClient: httpClient, Ledger: ledger, MaxRetries: 2}
}

func (c *Client) Deliver(ctx context.Context, job dispatch.Job) error {
    return c.deliverOnce(ctx, job)
}

func (c *Client) DeliverWithRetry(ctx context.Context, job dispatch.Job) error {
    if job.OperationKey == "" { return errors.New("operation key required") }
    return c.Ledger.Do(ctx, job.OperationKey, func() error {
        var lastErr error
        for attempt := 0; attempt <= c.MaxRetries; attempt++ {
            if err := ctx.Err(); err != nil { return err }
            err := c.deliverOnce(ctx, job)
            if err == nil { return nil }
            lastErr = err
            if !retryable(err) { return err }
        }
        return lastErr
    })
}

func retryable(err error) bool {
    var status *statusError
    if errors.As(err, &status) { return status.status >= 500 }
    return true
}

func (c *Client) deliverOnce(ctx context.Context, job dispatch.Job) error {
    var body []byte
    var err error
    if IsLegacyClient(job.ClientID) {
        body, err = BuildLegacyPayload(job.EventType, job.Payload)
    } else {
        body, err = BuildModernPayload(job.EventType, job.Payload)
    }
    if err != nil { return err }

    req, err := http.NewRequestWithContext(ctx, http.MethodPost, job.TargetURL, bytes.NewReader(body))
    if err != nil { return err }
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Idempotency-Key", job.OperationKey)
    resp, err := c.HTTPClient.Do(req)
    if err != nil { return err }
    defer resp.Body.Close()
    _, _ = io.Copy(io.Discard, resp.Body)
    if resp.StatusCode >= 400 { return &statusError{status: resp.StatusCode} }
    return nil
}

func (c *Client) SetTimeout(d time.Duration) { c.HTTPClient.Timeout = d }
GO
cat > /app/internal/delivery/payload.go <<'GO'
package delivery

import "encoding/json"

func BuildModernPayload(eventType string, fields map[string]string) ([]byte, error) {
    body := map[string]any{
        "event_type": eventType,
        "schema_version": "2",
        "trace_id": fields["trace_id"],
        "fields": fields,
    }
    return json.Marshal(body)
}

type legacyPayload struct {
    AccountID string `json:"account_id"`
    Amount string `json:"amount"`
    EventType string `json:"event_type"`
}

func BuildLegacyPayload(eventType string, fields map[string]string) ([]byte, error) {
    return json.Marshal(legacyPayload{
        AccountID: fields["account_id"],
        Amount: fields["amount"],
        EventType: eventType,
    })
}

func IsLegacyClient(clientID string) bool { return clientID == "legacy-v1" }
GO
