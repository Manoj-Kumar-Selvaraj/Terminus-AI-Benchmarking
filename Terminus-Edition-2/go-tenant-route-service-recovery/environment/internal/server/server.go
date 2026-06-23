package server

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"tenant-route-service/internal/proxy"
	"tenant-route-service/internal/routes"
)

type Service struct {
	Store  *routes.Store
	Proxy  *proxy.Client
	SLO    time.Duration
	Events chan string
}

func New(store *routes.Store, client *proxy.Client) *Service {
	return &Service{
		Store:  store,
		Proxy:  client,
		SLO:    0,
		Events: make(chan string, 128),
	}
}

func (s *Service) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/route/", s.route)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	return mux
}

func (s *Service) route(w http.ResponseWriter, r *http.Request) {
	tenant := r.URL.Path[len("/route/"):]
	route, ok := s.Store.Lookup(tenant)
	if !ok {
		http.Error(w, "tenant route not found", http.StatusNotFound)
		return
	}
	ctx := r.Context()
	result, err := s.Proxy.Fetch(ctx, route.Upstream)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	w.Header().Set("X-Route-Revision", fmt.Sprint(route.Revision))
	w.WriteHeader(result.StatusCode)
	_, _ = w.Write([]byte(result.Body))
}

func (s *Service) CloseWithServer(srv *http.Server) error {
	s.Events <- "termination-started"
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	return srv.Shutdown(ctx)
}

func (s *Service) ShutdownWithServer(ctx context.Context, srv *http.Server) error {
	s.Events <- "termination-started"
	return srv.Close()
}
