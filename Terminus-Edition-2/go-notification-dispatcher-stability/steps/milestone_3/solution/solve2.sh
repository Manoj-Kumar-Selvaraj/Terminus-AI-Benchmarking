#!/usr/bin/env bash
set -Eeuo pipefail
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
