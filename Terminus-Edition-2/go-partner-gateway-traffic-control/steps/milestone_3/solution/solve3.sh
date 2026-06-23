#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve2.sh"
cat > /app/internal/gateway/middleware.go <<'GOFILE'
package gateway

import (
    "encoding/json"
    "net/http"
    "strconv"
    "strings"

    "partner-gateway-traffic-control/internal/limiter"
)

type TrafficLimiter interface {
    Allow(identity string) limiter.Decision
}

type Middleware struct {
    limiter TrafficLimiter
    next    http.Handler
}

func NewMiddleware(trafficLimiter TrafficLimiter, next http.Handler) *Middleware {
    return &Middleware{limiter: trafficLimiter, next: next}
}

type errorResponse struct {
    Code         string `json:"code"`
    RetryAfterMS int64  `json:"retry_after_ms,omitempty"`
}

func (m *Middleware) ServeHTTP(response http.ResponseWriter, request *http.Request) {
    identity := requestIdentity(request.Header.Get("X-Tenant-ID"))
    decision := m.limiter.Allow(identity)
    response.Header().Set("X-RateLimit-Remaining", strconv.Itoa(decision.Remaining))
    if !decision.Allowed {
        retryAfterMS := decision.RetryAfter.Milliseconds()
        if retryAfterMS < 1 {
            retryAfterMS = 1
        }
        response.Header().Set("Retry-After-Ms", strconv.FormatInt(retryAfterMS, 10))
        writeJSON(response, http.StatusTooManyRequests, errorResponse{
            Code:         "rate_limited",
            RetryAfterMS: retryAfterMS,
        })
        return
    }

    m.next.ServeHTTP(response, request)
}

func requestIdentity(header string) string {
    normalized := strings.ToLower(strings.TrimSpace(header))
    if normalized == "" {
        return "identity/implicit-legacy"
    }
    return "identity/explicit/" + normalized
}

func writeJSON(response http.ResponseWriter, status int, body any) {
    response.Header().Set("Content-Type", "application/json")
    response.WriteHeader(status)
    _ = json.NewEncoder(response).Encode(body)
}
GOFILE
/usr/local/go/bin/gofmt -w /app/internal/gateway/middleware.go
