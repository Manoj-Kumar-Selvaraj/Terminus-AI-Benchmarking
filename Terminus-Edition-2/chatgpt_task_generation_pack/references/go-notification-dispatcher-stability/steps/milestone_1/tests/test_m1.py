import subprocess
from pathlib import Path

APP = Path("/app")

FILES = {'internal/dispatch/milestone_1_contract_test.go': 'package dispatch\n\nimport (\n    "context"\n    "fmt"\n    "sync"\n    "sync/atomic"\n    "testing"\n    "time"\n)\n\nfunc TestBurstEnqueuePreservesBoundedWorkerPool(t *testing.T) {\n    const workers = 4\n    const jobs = 48\n    var active atomic.Int32\n    var maxActive atomic.Int32\n    var completed atomic.Int32\n\n    d := NewDispatcher(workers, func(ctx context.Context, job Job) error {\n        now := active.Add(1)\n        for {\n            old := maxActive.Load()\n            if now <= old || maxActive.CompareAndSwap(old, now) {\n                break\n            }\n        }\n        time.Sleep(3 * time.Millisecond)\n        active.Add(-1)\n        completed.Add(1)\n        return nil\n    })\n\n    if got, want := cap(d.jobs), workers*4; got != want {\n        t.Fatalf("queue capacity = %d, want %d", got, want)\n    }\n\n    start := make(chan struct{})\n    var wg sync.WaitGroup\n    errCh := make(chan error, jobs)\n    for i := 0; i < jobs; i++ {\n        wg.Add(1)\n        go func(i int) {\n            defer wg.Done()\n            <-start\n            errCh <- d.Enqueue(Job{\n                OperationKey: fmt.Sprintf("op-%03d", i),\n                ClientID: "modern-default",\n                TargetURL: "http://example.invalid/hook",\n                EventType: "billing.credit",\n                Payload: map[string]string{"account_id": fmt.Sprint(i)},\n            })\n        }(i)\n    }\n    close(start)\n\n    enqueueDone := make(chan struct{})\n    go func() { wg.Wait(); close(enqueueDone) }()\n    select {\n    case <-enqueueDone:\n    case <-time.After(2 * time.Second):\n        t.Fatal("concurrent producers did not make bounded enqueue progress")\n    }\n    close(errCh)\n    for err := range errCh {\n        if err != nil {\n            t.Fatalf("unexpected enqueue error: %v", err)\n        }\n    }\n\n    deadline := time.Now().Add(3 * time.Second)\n    for completed.Load() != jobs && time.Now().Before(deadline) {\n        time.Sleep(2 * time.Millisecond)\n    }\n    if got := completed.Load(); got != jobs {\n        t.Fatalf("completed deliveries = %d, want %d", got, jobs)\n    }\n    if got := maxActive.Load(); got > workers {\n        t.Fatalf("delivery concurrency = %d, exceeds worker count %d", got, workers)\n    }\n    if got := d.QueueDepth(); got != 0 {\n        t.Fatalf("queue depth after drain = %d, want 0", got)\n    }\n}\n\nfunc TestInvalidJobDoesNotChangeDepth(t *testing.T) {\n    d := NewDispatcher(1, func(context.Context, Job) error { return nil })\n    before := d.QueueDepth()\n    if err := d.Enqueue(Job{}); err == nil {\n        t.Fatal("empty operation key was accepted")\n    }\n    if got := d.QueueDepth(); got != before {\n        t.Fatalf("queue depth changed from %d to %d after rejected job", before, got)\n    }\n}\n'}

def test_go_contracts():
    for relative, content in FILES.items():
        path = APP / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "-race", "./internal/dispatch", "./internal/delivery", "./internal/idempotency", "-count=1"],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
