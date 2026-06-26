package dispatch

import (
	"context"
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func sampleJob(key string) Job {
	return Job{
		OperationKey: key,
		ClientID:     "modern-default",
		TargetURL:    "http://example.invalid/hook",
		EventType:    "billing.credit",
		Payload:      map[string]string{"account_id": key},
	}
}

func TestBurstEnqueuePreservesBoundedWorkerPool(t *testing.T) {
	const workers = 4
	const jobs = 48
	var active atomic.Int32
	var maxActive atomic.Int32
	var completed atomic.Int32

	d := NewDispatcher(workers, func(ctx context.Context, job Job) error {
		now := active.Add(1)
		for {
			old := maxActive.Load()
			if now <= old || maxActive.CompareAndSwap(old, now) {
				break
			}
		}
		time.Sleep(3 * time.Millisecond)
		active.Add(-1)
		completed.Add(1)
		return nil
	})

	beforeGoroutines := runtime.NumGoroutine()

	start := make(chan struct{})
	var wg sync.WaitGroup
	errCh := make(chan error, jobs)
	for i := 0; i < jobs; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			errCh <- d.Enqueue(sampleJob(fmt.Sprintf("op-%03d", i)))
		}(i)
	}
	close(start)

	enqueueDone := make(chan struct{})
	go func() { wg.Wait(); close(enqueueDone) }()
	select {
	case <-enqueueDone:
	case <-time.After(2 * time.Second):
		t.Fatal("concurrent producers did not make bounded enqueue progress")
	}
	close(errCh)
	for err := range errCh {
		if err != nil {
			t.Fatalf("unexpected enqueue error: %v", err)
		}
	}

	deadline := time.Now().Add(3 * time.Second)
	for completed.Load() != jobs && time.Now().Before(deadline) {
		time.Sleep(2 * time.Millisecond)
	}
	if got := completed.Load(); got != jobs {
		t.Fatalf("completed deliveries = %d, want %d", got, jobs)
	}
	if got := maxActive.Load(); got > workers {
		t.Fatalf("delivery concurrency = %d, exceeds worker count %d", got, workers)
	}
	if got := d.QueueDepth(); got != 0 {
		t.Fatalf("queue depth after drain = %d, want 0", got)
	}
	if growth := runtime.NumGoroutine() - beforeGoroutines; growth > workers+8 {
		t.Fatalf("goroutine growth = %d exceeds bounded worker pool allowance", growth)
	}
}

func TestEnqueueBlocksUntilQueueHasSpace(t *testing.T) {
	const workers = 2
	const queueMultiplier = 4
	hold := make(chan struct{})
	started := make(chan struct{}, workers)
	var once sync.Once

	d := NewDispatcher(workers, func(ctx context.Context, job Job) error {
		once.Do(func() { close(started) })
		<-hold
		return nil
	})

	for i := 0; i < workers; i++ {
		if err := d.Enqueue(sampleJob(fmt.Sprintf("hold-%d", i))); err != nil {
			t.Fatalf("occupy worker %d: %v", i, err)
		}
	}
	select {
	case <-started:
	case <-time.After(500 * time.Millisecond):
		t.Fatal("workers did not start blocking deliveries")
	}

	for i := 0; i < workers*queueMultiplier; i++ {
		if err := d.Enqueue(sampleJob(fmt.Sprintf("buffer-%d", i))); err != nil {
			t.Fatalf("fill queue %d: %v", i, err)
		}
	}

	blocked := make(chan struct{})
	go func() {
		_ = d.Enqueue(sampleJob("should-block"))
		close(blocked)
	}()

	select {
	case <-blocked:
		t.Fatal("enqueue returned while the bounded queue was saturated")
	case <-time.After(150 * time.Millisecond):
	}

	close(hold)

	select {
	case <-blocked:
	case <-time.After(2 * time.Second):
		t.Fatal("enqueue remained blocked after queue space became available")
	}
}

func TestInvalidJobDoesNotChangeDepth(t *testing.T) {
	d := NewDispatcher(1, func(context.Context, Job) error { return nil })
	before := d.QueueDepth()
	if err := d.Enqueue(Job{}); err == nil {
		t.Fatal("empty operation key was accepted")
	}
	if got := d.QueueDepth(); got != before {
		t.Fatalf("queue depth changed from %d to %d after rejected job", before, got)
	}
}
