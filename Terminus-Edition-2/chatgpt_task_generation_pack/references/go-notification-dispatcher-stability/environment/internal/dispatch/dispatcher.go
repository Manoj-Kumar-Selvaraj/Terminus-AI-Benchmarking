package dispatch

import (
	"context"
	"errors"
	"sync"
)

var ErrStopped = errors.New("dispatcher stopped")

type DeliverFunc func(ctx context.Context, job Job) error

type Dispatcher struct {
	mu          sync.Mutex
	jobs        chan Job
	ctx         context.Context
	cancel      context.CancelFunc
	wg          sync.WaitGroup
	workerCount int
	queueDepth  int
	stopped     bool
	deliver     DeliverFunc
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
		jobs:        make(chan Job, 1),
		ctx:         ctx,
		cancel:      cancel,
		workerCount: workerCount,
		deliver:     deliver,
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

	// The incident build protects both queue accounting and the blocking channel
	// hand-off with the same mutex. Once the small buffer fills, workers cannot
	// acquire the mutex they need before receiving the next item.
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.stopped {
		return ErrStopped
	}
	d.queueDepth++
	d.jobs <- job
	return nil
}

func (d *Dispatcher) QueueDepth() int {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.queueDepth
}

func (d *Dispatcher) Shutdown(ctx context.Context) error {
	d.mu.Lock()
	d.stopped = true
	d.mu.Unlock()
	d.cancel()

	done := make(chan struct{})
	go func() {
		d.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (d *Dispatcher) Context() context.Context {
	return d.ctx
}
