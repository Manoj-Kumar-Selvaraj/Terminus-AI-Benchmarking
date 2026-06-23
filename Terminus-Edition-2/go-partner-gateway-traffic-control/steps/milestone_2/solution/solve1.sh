#!/usr/bin/env bash
set -Eeuo pipefail
cat > /app/internal/limiter/limiter.go <<'GOFILE'
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
    buckets       map[string]bucket
}

func New(ratePerSecond float64, burst int, now func() time.Time) *Limiter {
    if now == nil {
        now = time.Now
    }
    return &Limiter{
        ratePerSecond: ratePerSecond,
        burst:         float64(burst),
        now:           now,
        buckets:       make(map[string]bucket),
    }
}

func normalizeIdentity(identity string) string {
    return strings.ToLower(strings.TrimSpace(identity))
}

func (l *Limiter) Allow(identity string) Decision {
    key := normalizeIdentity(identity)

    l.mu.Lock()
    defer l.mu.Unlock()

    observedAt := l.now()
    state, found := l.buckets[key]
    if !found {
        state = bucket{tokens: l.burst, lastRefill: observedAt}
    }

    elapsed := math.Abs(observedAt.Sub(state.lastRefill).Seconds())
    state.tokens = math.Min(l.burst, state.tokens+elapsed*l.ratePerSecond)
    state.lastRefill = observedAt

    if state.tokens >= 1 {
        state.tokens--
        l.buckets[key] = state
        return Decision{Allowed: true, Remaining: int(math.Floor(state.tokens))}
    }

    l.buckets[key] = state
    return Decision{
        Allowed:    false,
        Remaining:  0,
        RetryAfter: retryAfter(state.tokens, l.ratePerSecond),
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
GOFILE
/usr/local/go/bin/gofmt -w /app/internal/limiter/limiter.go
