package limiter

import (
	"math"
	"strings"
	"sync"
	"time"
)

type Decision struct {
	Allowed    bool
	Remaining  int
	RetryAfter time.Duration
}

type bucket struct {
	tokens     float64
	lastRefill time.Time
}

type Limiter struct {
	mu            sync.Mutex
	ratePerSecond float64
	burst         float64
	now           func() time.Time
	shared        bucket
}

func New(ratePerSecond float64, burst int, now func() time.Time) *Limiter {
	if now == nil {
		now = time.Now
	}
	createdAt := now()
	return &Limiter{
		ratePerSecond: ratePerSecond,
		burst:         float64(burst),
		now:           now,
		shared: bucket{
			tokens:     float64(burst),
			lastRefill: createdAt,
		},
	}
}

func normalizeIdentity(identity string) string {
	return strings.ToLower(strings.TrimSpace(identity))
}

func (l *Limiter) Allow(identity string) Decision {
	_ = normalizeIdentity(identity)

	l.mu.Lock()
	defer l.mu.Unlock()

	observedAt := l.now()
	elapsed := math.Abs(observedAt.Sub(l.shared.lastRefill).Seconds())
	l.shared.tokens = math.Min(l.burst, l.shared.tokens+elapsed*l.ratePerSecond)
	l.shared.lastRefill = observedAt

	if l.shared.tokens >= 1 {
		l.shared.tokens--
		return Decision{Allowed: true, Remaining: int(math.Floor(l.shared.tokens))}
	}

	return Decision{
		Allowed:    false,
		Remaining:  0,
		RetryAfter: retryAfter(l.shared.tokens, l.ratePerSecond),
	}
}

func retryAfter(tokens, ratePerSecond float64) time.Duration {
	if ratePerSecond <= 0 {
		return time.Hour
	}
	seconds := (1 - tokens) / ratePerSecond
	if seconds < 0 {
		seconds = 0
	}
	return time.Duration(math.Ceil(seconds * float64(time.Second)))
}
