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
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-ID"))
	if tenantID == "" {
		writeJSON(response, http.StatusBadRequest, errorResponse{Code: "tenant_required"})
		return
	}

	decision := m.limiter.Allow(tenantID)
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

func writeJSON(response http.ResponseWriter, status int, body any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(body)
}
