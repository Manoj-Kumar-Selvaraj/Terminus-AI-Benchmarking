package idempotency

import "sync"

type Ledger struct {
	mu        sync.Mutex
	delivered map[string]struct{}
}

func NewLedger() *Ledger {
	return &Ledger{delivered: map[string]struct{}{}}
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
